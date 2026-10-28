"""load_json — load a JSON file with pandas."""
import json
from pathlib import Path


async def load_json(path: str = None, data: str = None) -> dict:
    """
    Load JSON and normalize into a DataFrame.

    Args:
        path: path to a .json file (or omit and pass data)
        data: raw JSON string

    Returns:
        {"ok": True, "rows": int, "columns": [...], "preview": [...]}
    """
    import pandas as pd
    if path:
        f = Path(path)
        if not f.exists():
            raise FileNotFoundError(f"JSON not found: {path}")
        raw = f.read_text(encoding="utf-8")
    elif data:
        raw = data
    else:
        raise ValueError("provide 'path' or 'data'")

    obj = json.loads(raw)
    if isinstance(obj, list):
        df = pd.json_normalize(obj)
    elif isinstance(obj, dict):
        try:
            df = pd.json_normalize(obj)
        except Exception:
            df = pd.DataFrame([obj])
    else:
        raise ValueError(f"unsupported JSON root: {type(obj).__name__}")

    return {"ok": True, "rows": len(df), "columns": list(df.columns),
            "preview": df.head(5).to_dict(orient="records")}
