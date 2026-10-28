"""decrypt_pdf — remove password protection."""
from pathlib import Path


async def decrypt_pdf(path: str, password: str, output_path: str = None) -> dict:
    """
    Decrypt a password-protected PDF.

    Args:
        path: encrypted PDF
        password: the current password
        output_path: destination (default: <name>_decrypted.pdf)

    Returns:
        {"ok": True, "output": str, "pages": int}
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")

    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    out = output_path or f"{src.stem}_decrypted.pdf"

    reader = PdfReader(str(src))
    if reader.is_encrypted:
        result = reader.decrypt(password)
        if result == 0:
            raise ValueError("Wrong password")

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    with open(out, "wb") as fh:
        writer.write(fh)

    return {"ok": True, "output": out, "pages": len(writer.pages),
            "bytes": Path(out).stat().st_size}
