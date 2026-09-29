"""
Data Upload Pipeline — streaming, format detection, PII detection, indexing.

Supports CSV, JSON, JSONL, XLSX, Parquet, SQLite.
Max upload size: 10 GB per file (configurable).
Streaming chunk upload with SHA256 incremental validation.

PII detection: regex-based on common patterns. Restricted columns are
NOT indexed in semantic memory unless explicitly approved.
"""
import os
import re
import csv
import json
import time
import hashlib
import sqlite3
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, AsyncIterator
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum


DATA_DIR = Path(os.getenv("EMPIRE_DATA_DIR", "/workspace/ai-empire/empire_data"))
MAX_FILE_SIZE = int(os.getenv("EMPIRE_MAX_UPLOAD_BYTES", str(10 * 1024**3)))  # 10 GB
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB chunks


class FileFormat(str, Enum):
    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"
    XLSX = "xlsx"
    PARQUET = "parquet"
    SQLITE = "sqlite"
    UNKNOWN = "unknown"


@dataclass
class PIIColumn:
    column: str
    pattern: str
    sample: str  # redacted sample
    count: int


@dataclass
class DataSchema:
    columns: List[Dict[str, str]]  # [{name, type, sample}]
    row_count: int
    format: str
    file_size: int
    has_header: bool
    pii_columns: List[PIIColumn] = field(default_factory=list)
    pii_redacted: bool = False


@dataclass
class Dataset:
    id: str
    name: str
    filename: str
    format: FileFormat
    path: Path
    schema: DataSchema
    size_bytes: int
    sha256: str
    uploaded_at: str
    tenant: str
    indexed: bool = False
    pii_detected: bool = False
    indexed_rows: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── PII patterns ───────────────────────────────────────────────────────────

PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone_br": re.compile(r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}-?\d{4}\b"),
    "cpf": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b"),
    "api_key": re.compile(r"\b(?:sk|pk|api)[-_][A-Za-z0-9]{16,}\b"),
    "bearer": re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"),
}


def detect_pii(value: Any) -> Optional[str]:
    """Detect PII in a single value. Returns pattern name or None."""
    if value is None:
        return None
    s = str(value)
    for name, pattern in PII_PATTERNS.items():
        if pattern.search(s):
            return name
    return None


def redact_pii(value: Any, pattern: str) -> str:
    """Return redacted version of value."""
    s = str(value)
    if pattern == "email":
        return "[EMAIL]"
    if pattern == "phone_br":
        return "[PHONE]"
    if pattern == "cpf":
        return "[CPF]"
    if pattern == "credit_card":
        return "[CC]"
    if pattern == "ssn":
        return "[SSN]"
    if pattern == "ip":
        return "[IP]"
    if pattern == "iban":
        return "[IBAN]"
    if pattern == "api_key":
        return "[API_KEY]"
    if pattern == "bearer":
        return "Bearer [REDACTED]"
    return "[REDACTED]"


def infer_column_type(values: List[Any]) -> str:
    """Infer the type of a column based on sample values."""
    if not values:
        return "unknown"
    has_int = has_float = has_str = has_date = False
    for v in values[:50]:
        if v is None or v == "":
            continue
        if isinstance(v, (int, bool)):
            has_int = True
        elif isinstance(v, float):
            has_float = True
        elif isinstance(v, str):
            has_str = True
            try:
                # Try parsing common date formats
                if re.match(r"\d{4}-\d{2}-\d{2}", v):
                    has_date = True
            except Exception:
                pass
    if has_int and not has_float and not has_str:
        return "integer"
    if (has_int or has_float) and not has_str:
        return "float"
    if has_date:
        return "date"
    if has_str:
        return "string"
    return "mixed"


# ─── Format detection ───────────────────────────────────────────────────────

def detect_format(path: Path) -> FileFormat:
    """Detect file format by extension and magic bytes."""
    ext = path.suffix.lower()
    if ext == ".csv":
        return FileFormat.CSV
    if ext == ".json":
        return FileFormat.JSON
    if ext in (".jsonl", ".ndjson"):
        return FileFormat.JSONL
    if ext == ".xlsx":
        return FileFormat.XLSX
    if ext == ".parquet":
        return FileFormat.PARQUET
    if ext in (".sqlite", ".db", ".sqlite3"):
        return FileFormat.SQLITE
    # Magic bytes sniff
    try:
        with open(path, "rb") as f:
            head = f.read(16)
        if head.startswith(b"PK\x03\x04"):  # XLSX is a zip
            return FileFormat.XLSX
        if head.startswith(b"PAR1"):
            return FileFormat.PARQUET
        if head.startswith(b"SQLite format 3"):
            return FileFormat.SQLITE
        if head.startswith(b"["):
            return FileFormat.JSON
        if head.startswith(b"{"):
            return FileFormat.JSON
    except Exception:
        pass
    return FileFormat.UNKNOWN


# ─── Schema extraction ──────────────────────────────────────────────────────

def extract_csv_schema(path: Path, max_rows: int = 1000) -> DataSchema:
    """Extract schema from CSV file."""
    columns = []
    row_count = 0
    sample_values: Dict[str, List] = {}
    pii_columns = []
    pii_detected = False
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for col in headers:
            sample_values[col] = []
        for row in reader:
            row_count += 1
            if row_count <= max_rows:
                for col in headers:
                    sample_values[col].append(row.get(col))
        # Infer types and detect PII
        for col in headers:
            samples = [v for v in sample_values[col] if v not in (None, "")]
            col_type = infer_column_type(samples)
            sample_repr = str(samples[0])[:50] if samples else ""
            columns.append({"name": col, "type": col_type, "sample": sample_repr})
            # Detect PII
            for sample in samples[:20]:
                pii = detect_pii(sample)
                if pii:
                    pii_columns.append(PIIColumn(
                        column=col, pattern=pii,
                        sample=redact_pii(sample, pii),
                        count=sum(1 for s in samples if detect_pii(s))
                    ))
                    pii_detected = True
                    break
    return DataSchema(
        columns=columns, row_count=row_count,
        format=FileFormat.CSV.value, file_size=path.stat().st_size,
        has_header=True, pii_columns=pii_columns, pii_redacted=False
    )


def extract_jsonl_schema(path: Path, max_rows: int = 1000) -> DataSchema:
    """Extract schema from JSONL file."""
    columns = {}
    row_count = 0
    pii_detected = False
    pii_columns = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            row_count += 1
            if not isinstance(row, dict):
                continue
            if row_count <= max_rows:
                for k, v in row.items():
                    if k not in columns:
                        columns[k] = {"name": k, "type": "unknown", "sample": "", "values": []}
                    columns[k]["values"].append(v)
                    if not columns[k]["sample"]:
                        columns[k]["sample"] = str(v)[:50]
            if row_count > max_rows:
                break
    for col in columns.values():
        col["type"] = infer_column_type(col["values"])
        # Detect PII
        for sample in col["values"][:20]:
            pii = detect_pii(sample)
            if pii:
                pii_columns.append(PIIColumn(
                    column=col["name"], pattern=pii,
                    sample=redact_pii(sample, pii),
                    count=sum(1 for s in col["values"] if detect_pii(s))
                ))
                pii_detected = True
                break
    # Drop values from final schema
    columns_clean = [{"name": c["name"], "type": c["type"], "sample": c["sample"]} for c in columns.values()]
    return DataSchema(
        columns=columns_clean, row_count=row_count,
        format=FileFormat.JSONL.value, file_size=path.stat().st_size,
        has_header=True, pii_columns=pii_columns, pii_redacted=False
    )


def extract_json_schema(path: Path) -> DataSchema:
    """Extract schema from JSON file (single object or array)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return extract_jsonl_schema(path)  # Same logic
    elif isinstance(data, dict):
        # Single object — treat as one row
        columns = []
        pii_columns = []
        for k, v in data.items():
            col_type = infer_column_type([v])
            sample = str(v)[:50]
            columns.append({"name": k, "type": col_type, "sample": sample})
            pii = detect_pii(v)
            if pii:
                pii_columns.append(PIIColumn(
                    column=k, pattern=pii,
                    sample=redact_pii(v, pii), count=1
                ))
        return DataSchema(
            columns=columns, row_count=1,
            format=FileFormat.JSON.value, file_size=path.stat().st_size,
            has_header=True, pii_columns=pii_columns, pii_redacted=False
        )
    return DataSchema(
        columns=[], row_count=0,
        format=FileFormat.JSON.value, file_size=path.stat().st_size,
        has_header=False
    )


def extract_schema(path: Path, fmt: FileFormat) -> DataSchema:
    if fmt == FileFormat.CSV:
        return extract_csv_schema(path)
    if fmt == FileFormat.JSONL:
        return extract_jsonl_schema(path)
    if fmt == FileFormat.JSON:
        return extract_json_schema(path)
    return DataSchema(
        columns=[], row_count=0, format=fmt.value,
        file_size=path.stat().st_size, has_header=False
    )


# ─── Dataset store ──────────────────────────────────────────────────────────

class DatasetStore:
    """Manages uploaded datasets per tenant."""

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._datasets: Dict[str, Dataset] = {}
        self._load_metadata()

    def _load_metadata(self):
        meta_file = self.data_dir / "datasets.json"
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text())
                for ds_data in data.get("datasets", []):
                    ds = Dataset(
                        id=ds_data["id"], name=ds_data["name"],
                        filename=ds_data["filename"],
                        format=FileFormat(ds_data["format"]),
                        path=Path(ds_data["path"]),
                        schema=DataSchema(**{k: v for k, v in ds_data["schema"].items()
                                           if k != "pii_columns"}) if ds_data.get("schema") else DataSchema([], 0, "unknown", 0, False),
                        size_bytes=ds_data["size_bytes"],
                        sha256=ds_data["sha256"],
                        uploaded_at=ds_data["uploaded_at"],
                        tenant=ds_data["tenant"],
                        indexed=ds_data.get("indexed", False),
                        pii_detected=ds_data.get("pii_detected", False),
                        indexed_rows=ds_data.get("indexed_rows", 0),
                    )
                    self._datasets[ds.id] = ds
            except Exception as e:
                print(f"[data] failed to load metadata: {e}")

    def _save_metadata(self):
        meta = {"version": 1, "datasets": []}
        for ds in self._datasets.values():
            meta["datasets"].append({
                "id": ds.id, "name": ds.name, "filename": ds.filename,
                "format": ds.format.value, "path": str(ds.path),
                "schema": asdict(ds.schema),
                "size_bytes": ds.size_bytes, "sha256": ds.sha256,
                "uploaded_at": ds.uploaded_at, "tenant": ds.tenant,
                "indexed": ds.indexed, "pii_detected": ds.pii_detected,
                "indexed_rows": ds.indexed_rows,
            })
        (self.data_dir / "datasets.json").write_text(json.dumps(meta, indent=2, default=str))

    def _tenant_dir(self, tenant: str) -> Path:
        d = self.data_dir / f"tenant_{tenant}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def save_streaming(
        self, filename: str, stream: AsyncIterator[bytes],
        tenant: str = "default", expected_sha256: str = "",
        progress_callback=None,
    ) -> Dataset:
        """Save a streaming upload to disk. Returns Dataset on success."""
        # Validate filename
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
        if not safe_name:
            raise ValueError("invalid filename")

        # Determine format
        fmt = detect_format(Path(safe_name))
        if fmt == FileFormat.UNKNOWN:
            raise ValueError(f"unsupported format: {safe_name}")

        # Save to temp file first
        dest = self._tenant_dir(tenant) / safe_name
        sha256 = hashlib.sha256()
        total = 0
        with tempfile.NamedTemporaryFile(delete=False, dir=str(self._tenant_dir(tenant))) as tmp:
            tmp_path = Path(tmp.name)
            async for chunk in stream:
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    tmp_path.unlink()
                    raise ValueError(f"file too large: {total} > {MAX_FILE_SIZE}")
                sha256.update(chunk)
                tmp.write(chunk)
                if progress_callback:
                    await progress_callback(total)
            tmp.flush()
        # Move to final destination
        tmp_path.rename(dest)

        # Verify SHA256 if expected
        actual_sha = "sha256:" + sha256.hexdigest()
        if expected_sha256 and expected_sha256 != actual_sha:
            dest.unlink()
            raise ValueError(f"SHA256 mismatch: expected={expected_sha256}, got={actual_sha}")

        # Extract schema
        schema = extract_schema(dest, fmt)

        ds = Dataset(
            id=f"ds-{int(time.time() * 1000)}-{sha256.hexdigest()[:6]}",
            name=Path(safe_name).stem,
            filename=safe_name,
            format=fmt,
            path=dest,
            schema=schema,
            size_bytes=total,
            sha256=actual_sha,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
            tenant=tenant,
            pii_detected=bool(schema.pii_columns),
        )
        self._datasets[ds.id] = ds
        self._save_metadata()
        return ds

    def list(self, tenant: str = None) -> List[Dataset]:
        items = list(self._datasets.values())
        if tenant:
            items = [d for d in items if d.tenant == tenant]
        return sorted(items, key=lambda d: d.uploaded_at, reverse=True)

    def get(self, ds_id: str) -> Optional[Dataset]:
        return self._datasets.get(ds_id)

    def delete(self, ds_id: str):
        ds = self._datasets.get(ds_id)
        if not ds:
            raise KeyError(ds_id)
        if ds.path.exists():
            ds.path.unlink()
        del self._datasets[ds_id]
        self._save_metadata()

    def query(self, ds_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Query rows from a dataset. Returns redacted data if PII was detected."""
        ds = self._datasets.get(ds_id)
        if not ds:
            raise KeyError(ds_id)
        if ds.format == FileFormat.CSV:
            return self._query_csv(ds, limit, offset)
        if ds.format == FileFormat.JSONL:
            return self._query_jsonl(ds, limit, offset)
        return []

    def _query_csv(self, ds: Dataset, limit: int, offset: int) -> List[Dict[str, Any]]:
        results = []
        with open(ds.path, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i < offset:
                    continue
                if len(results) >= limit:
                    break
                # Redact PII columns
                if ds.pii_detected:
                    for pii_col in ds.schema.pii_columns:
                        if pii_col.column in row:
                            row[pii_col.column] = redact_pii(row[pii_col.column], pii_col.pattern)
                results.append(row)
        return results

    def _query_jsonl(self, ds: Dataset, limit: int, offset: int) -> List[Dict[str, Any]]:
        results = []
        with open(ds.path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                if i < offset:
                    continue
                if len(results) >= limit:
                    break
                row = json.loads(line)
                if ds.pii_detected:
                    for pii_col in ds.schema.pii_columns:
                        if pii_col.column in row:
                            row[pii_col.column] = redact_pii(row[pii_col.column], pii_col.pattern)
                results.append(row)
        return results

    def stats(self) -> Dict[str, Any]:
        """Aggregate stats for the dashboard."""
        items = list(self._datasets.values())
        total_size = sum(d.size_bytes for d in items)
        by_format = {}
        pii_count = sum(1 for d in items if d.pii_detected)
        for d in items:
            by_format[d.format.value] = by_format.get(d.format.value, 0) + 1
        return {
            "dataset_count": len(items),
            "total_size_bytes": total_size,
            "total_size_human": _human_bytes(total_size),
            "by_format": by_format,
            "pii_datasets": pii_count,
            "indexed_datasets": sum(1 for d in items if d.indexed),
            "limit_bytes": MAX_FILE_SIZE,
            "limit_human": _human_bytes(MAX_FILE_SIZE),
        }


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ─── Singleton ──────────────────────────────────────────────────────────────

_STORE: Optional[DatasetStore] = None


def get_store() -> DatasetStore:
    global _STORE
    if _STORE is None:
        _STORE = DatasetStore()
    return _STORE
