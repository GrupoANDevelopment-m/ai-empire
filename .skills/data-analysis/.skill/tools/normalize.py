"""normalize — min-max, z-score, robust scaling."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df
from describe import _safe


async def normalize(**kwargs) -> dict:
    """
    Normalize numeric columns.

    Args:
        data: dataset
        columns: columns to scale (default: all numeric)
        method: minmax | zscore | robust

    Returns:
        {"ok": True, "method": str, "data": {...}}
    """
    import numpy as np
    import pandas as pd
    df = load_df(kwargs.get("data"), kwargs.get("path")).copy()
    cols = kwargs.get("columns") or list(df.select_dtypes(include="number").columns)
    m = kwargs.get("method", "minmax")
    for c in cols:
        if c not in df.columns:
            continue
        s = df[c].astype(float)
        if m == "minmax":
            lo, hi = s.min(), s.max()
            df[c] = (s - lo) / (hi - lo) if hi != lo else 0.0
        elif m == "zscore":
            mu, sd = s.mean(), s.std()
            df[c] = (s - mu) / sd if sd else 0.0
        elif m == "robust":
            med = s.median()
            iqr = s.quantile(0.75) - s.quantile(0.25)
            df[c] = (s - med) / iqr if iqr else 0.0
        else:
            raise ValueError(f"unknown method: {m}")
    return {"ok": True, "method": m, "columns": cols,
            "data": _safe(df.to_dict(orient="records"))}
