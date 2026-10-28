"""extract_text — real text extraction from PDF pages."""
from pathlib import Path


async def extract_text(path: str, pages: str = None, layout: bool = False) -> dict:
    """
    Extract text from a PDF.

    Args:
        path: PDF file path
        pages: optional page range like "1-5" or "1,3,7" (default: all)
        layout: preserve layout (slower)

    Returns:
        {"ok": True, "text": str, "page_count": int, "chars": int}
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    reader = PdfReader(str(p))
    idx = range(len(reader.pages))
    if pages:
        wanted = []
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-")
                wanted.extend(range(int(a) - 1, int(b)))
            elif part.isdigit():
                wanted.append(int(part) - 1)
        idx = [i for i in wanted if 0 <= i < len(reader.pages)]

    chunks = []
    for i in idx:
        chunks.append(reader.pages[i].extract_text(extraction_mode="layout" if layout else "plain"))

    text = "\n\n".join(chunks)
    return {"ok": True, "text": text, "page_count": len(idx), "chars": len(text),
            "path": path}
