"""encrypt_pdf — real AES PDF encryption."""
from pathlib import Path


async def encrypt_pdf(path: str, password: str, output_path: str = None) -> dict:
    """
    Encrypt a PDF with a user password.

    Args:
        path: source PDF
        password: the password to set
        output_path: destination (default: <name>_encrypted.pdf)

    Returns:
        {"ok": True, "output": str, "encrypted": True}
    """
    try:
        from pypdf import PdfWriter, PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")

    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    out = output_path or f"{src.stem}_encrypted.pdf"

    reader = PdfReader(str(src))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password, algorithm="AES-256")

    with open(out, "wb") as fh:
        writer.write(fh)

    return {"ok": True, "output": out, "encrypted": True,
            "bytes": Path(out).stat().st_size}
