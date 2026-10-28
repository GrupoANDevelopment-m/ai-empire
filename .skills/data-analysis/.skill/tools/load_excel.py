"""load_excel — load an Excel sheet with pandas."""
from pathlib import Path


async def load_excel(path: str, sheet_name=0, nrows: int = None) -> dict:
    """
    Load an Excel file.

    Args:
        path: .xlsx path
        sheet_name: sheet name or index
        nrows: limit rows

    Returns:
        {"ok": True, "rows": int, "columns": [...], "sheets": [...]}
    """
    import pandas as pd
    f = Path(path)
    if not f.exists():
        raise FileNotFoundError(f"Excel not found: {path}")
    xls = pd.ExcelFile(f)
    df = pd.read_excel(f, sheet_name=sheet_name, nrows=nrows)
    return {"ok": True, "rows": len(df), "columns": list(df.columns),
            "sheets": xls.sheet_names,
            "preview": df.head(5).to_dict(orient="records")}
