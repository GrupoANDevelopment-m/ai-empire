"""merge_pdfs — real PDF merge with pypdf."""
from pathlib import Path


async def merge_pdfs(input_paths: list, output_path: str = "merged.pdf") -> dict:
    """
    Merge multiple PDFs into one.

    Args:
        input_paths: list of PDF paths to merge in order
        output_path: destination path

    Returns:
        {"ok": True, "merged": int, "output": str, "bytes": int}
    """
    try:
        from pypdf import PdfWriter
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")

    if not input_paths:
        raise ValueError("input_paths cannot be empty")

    writer = PdfWriter()
    for src in input_paths:
        p = Path(src)
        if not p.exists():
            raise FileNotFoundError(f"PDF not found: {src}")
        writer.append(str(p))

    with open(output_path, "wb") as fh:
        writer.write(fh)

    return {"ok": True, "merged": len(input_paths), "output": output_path,
            "bytes": Path(output_path).stat().st_size,
            "pages": len(writer.pages)}
