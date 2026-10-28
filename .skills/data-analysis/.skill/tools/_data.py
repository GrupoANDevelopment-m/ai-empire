"""Shared dataframe loader for data-analysis tools."""
import json, csv, io
from pathlib import Path


def load_df(data=None, path=None):
    """Build a pandas DataFrame from a dict/list-of-dicts or a file."""
    import pandas as pd
    if data is not None:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                raise ValueError("data is a string but not valid JSON")
        if isinstance(data, list):
            if not data:
                raise ValueError("data list is empty")
            return pd.DataFrame(data)
        if isinstance(data, dict):
            try:
                return pd.DataFrame(data)
            except Exception:
                return pd.DataFrame([data])
        raise ValueError(f"unsupported data type: {type(data).__name__}")
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"file not found: {path}")
        ext = p.suffix.lower()
        if ext in (".csv", ".txt"):
            return pd.read_csv(p)
        if ext in (".json",):
            return pd.read_json(p)
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(p)
        if ext in (".parquet",):
            return pd.read_parquet(p)
        raise ValueError(f"unsupported file type: {ext}")
    raise ValueError("provide either 'data' or 'path'")
