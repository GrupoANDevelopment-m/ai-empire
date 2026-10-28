"""extract_images — real image extraction from PDFs."""
from pathlib import Path


async def extract_images(path: str, output_dir: str = "pdf_images", min_size: int = 5000) -> dict:
    """
    Extract embedded images from a PDF.

    Args:
        path: source PDF
        output_dir: destination folder
        min_size: skip images smaller than this (bytes)

    Returns:
        {"ok": True, "images": [...], "count": int}
    """
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []

    try:
        from pypdf import PdfReader
        reader = PdfReader(str(src))
        for pno, page in enumerate(reader.pages, 1):
            for idx, img in enumerate(page.images):
                data = img.data
                if len(data) < min_size:
                    continue
                dest = out / f"{src.stem}_p{pno:03d}_{idx}{Path(img.name).suffix or '.png'}"
                dest.write_bytes(data)
                saved.append({"path": str(dest), "bytes": len(data), "page": pno})
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")

    return {"ok": True, "images": saved, "count": len(saved)}
