"""load_csv — load a CSV file with pandas."""
from pathlib import Path


async def load_csv(path: str, delimiter: str = ",", encoding: str = "utf-8", nrows: int = None) -> dict:
    """
    Load a CSV file and return shape + preview.

    Args:
        path: CSV file path or URL
        delimiter: column delimiter
        encoding: file encoding
        nrows: read only the first N rows

    Returns:
        {"ok": True, "rows": int, "columns": [...], "dtypes": {...}, "preview": [...]}
    """
    import pandas as pd
    p = str(path)
    if p.startswith("http"):
        df = pd.read_csv(p, delimiter=delimiter, nrows=nrows)
    else:
        f = Path(p)
        if not f.exists():
            raise FileNotFoundError(f"CSV not found: {path}")
        df = pd.read_csv(f, delimiter=delimiter, encoding=encoding, nrows=nrows)
    return {"ok": True, "rows": len(df), "columns": list(df.columns),
            "dtypes": {c: str(t) for c, t in df.dtypes.items()},
            "preview": df.head(5).to_dict(orient="records"),
            "memory_bytes": int(df.memory_usage(deep=True).sum())}
