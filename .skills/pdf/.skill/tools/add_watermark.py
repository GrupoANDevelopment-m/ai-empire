"""add_watermark — real watermark overlay using pypdf + reportlab."""
from pathlib import Path


async def add_watermark(path: str, text: str = "CONFIDENTIAL", output_path: str = None,
                        opacity: float = 0.25, angle: int = 45) -> dict:
    """
    Stamp a diagonal watermark on every page of a PDF.

    Args:
        path: source PDF
        text: watermark text
        output_path: destination (default: <name>_watermarked.pdf)
        opacity: 0.0-1.0
        angle: degrees

    Returns:
        {"ok": True, "output": str, "pages": int, "bytes": int}
    """
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import grey
    except ImportError:
        raise RuntimeError("pypdf + reportlab required. Run: pip install pypdf reportlab")

    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    out = output_path or f"{src.stem}_watermarked.pdf"

    reader = PdfReader(str(src))
    writer = PdfWriter()
    w, h = reader.pages[0].mediabox.width, reader.pages[0].mediabox.height

    for page in reader.pages:
        buf = __import__("io").BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.saveState()
        c.setFillColor(grey, alpha=opacity)
        c.setFont("Helvetica-Bold", 48)
        c.translate(w / 2, h / 2)
        c.rotate(angle)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.showPage()
        c.save()
        buf.seek(0)
        from pypdf import PdfReader as R2
        watermark = R2(buf).pages[0]
        page.merge_page(watermark)
        writer.add_page(page)

    with open(out, "wb") as fh:
        writer.write(fh)

    return {"ok": True, "output": out, "pages": len(writer.pages),
            "bytes": Path(out).stat().st_size, "watermark": text}
