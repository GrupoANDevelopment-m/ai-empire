"""pdf_to_image — real PDF rasterization with pdftoppm/poppler."""
import shutil
import subprocess
from pathlib import Path


async def pdf_to_image(path: str, output_dir: str = "pdf_pages", dpi: int = 150,
                       fmt: str = "png") -> dict:
    """
    Rasterize PDF pages to images using poppler's pdftoppm.

    Args:
        path: source PDF
        output_dir: destination folder
        dpi: resolution
        fmt: png | jpeg

    Returns:
        {"ok": True, "images": [...], "count": int}
    """
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm not found. Install poppler-utils: apt-get install poppler-utils")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = out / src.stem

    cmd = ["pdftoppm", "-png" if fmt == "png" else "-jpeg",
           "-r", str(dpi), str(src), str(prefix)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {proc.stderr[:300]}")

    images = sorted(str(p) for p in out.glob(f"{src.stem}*"))
    return {"ok": True, "images": images, "count": len(images), "dpi": dpi}
