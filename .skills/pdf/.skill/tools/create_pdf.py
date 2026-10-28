"""create_pdf — create a real PDF from text/HTML using reportlab."""
import io
from pathlib import Path


async def create_pdf(title: str = "Document", body: str = "", output_path: str = None) -> dict:
    """
    Create a PDF file from text content.

    Args:
        title: PDF title (also becomes the heading)
        body: text content for the PDF body
        output_path: where to write. If omitted, returns base64 only.

    Returns:
        {"ok": True, "path": str, "bytes": int, "pages": int}
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except ImportError:
        raise RuntimeError("reportlab not installed. Run: pip install reportlab")

    if not output_path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:50]
        output_path = f"{safe or 'document'}.pdf"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("EmpireTitle", parent=styles["Title"], fontSize=22, spaceAfter=18)
    body_style = ParagraphStyle("EmpireBody", parent=styles["BodyText"], fontSize=11, leading=16)

    # Escape XML for reportlab Paragraph
    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    story = [Paragraph(esc(title), title_style), Spacer(1, 12)]
    for para in body.split("\n\n"):
        story.append(Paragraph(esc(para).replace("\n", "<br/>"), body_style))
        story.append(Spacer(1, 8))

    doc = SimpleDocTemplate(output_path, pagesize=A4, title=title,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    doc.build(story)
    size = Path(output_path).stat().st_size
    return {"ok": True, "path": output_path, "bytes": size, "title": title}
