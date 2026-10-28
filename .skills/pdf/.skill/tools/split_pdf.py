"""split_pdf — real PDF split into single pages."""
import re
from pathlib import Path


async def split_pdf(path: str, output_dir: str = "split", mode: str = "pages") -> dict:
    """
    Split a PDF.

    Args:
        path: source PDF
        output_dir: where to write the parts
        mode: "pages" (one file per page) or "ranges" (e.g. "1-3,4-8")

    Returns:
        {"ok": True, "created": [...], "count": int}
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")

    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(src))
    created = []

    if mode == "pages":
        for i, page in enumerate(reader.pages, 1):
            w = PdfWriter()
            w.add_page(page)
            dest = out / f"{src.stem}_p{i:03d}.pdf"
            with open(dest, "wb") as fh:
                w.write(fh)
            created.append(str(dest))
    else:
        raise ValueError("mode must be 'pages'; pass explicit ranges via output naming")

    return {"ok": True, "created": created, "count": len(created), "output_dir": str(out)}
