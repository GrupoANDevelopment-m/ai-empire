"""parse_pdf — real PDF parsing with pypdf."""
from pathlib import Path


def _reader(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise RuntimeError("pypdf not installed. Run: pip install pypdf")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    return PdfReader(str(p))


async def parse_pdf(path: str) -> dict:
    """
    Parse a PDF and return metadata + structure.

    Args:
        path: path to the PDF file

    Returns:
        {"ok": True, "pages": int, "metadata": {...}, "encrypted": bool}
    """
    reader = _reader(path)
    meta = {}
    if reader.metadata:
        for k, v in reader.metadata.items():
            meta[str(k).lstrip("/")] = str(v)
    return {
        "ok": True,
        "pages": len(reader.pages),
        "metadata": meta,
        "encrypted": reader.is_encrypted,
        "size_bytes": Path(path).stat().st_size,
    }
