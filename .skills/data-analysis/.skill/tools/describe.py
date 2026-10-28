"""describe — statistical summary of a dataset."""
import sys, os, json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df


def _safe(o):
    """Make a value JSON-serialisable: NaN/Inf become None, numpy -> native.

    pandas' to_dict() yields *plain* Python floats for missing cells, and a
    plain float is not an np.floating — so NaN must be checked on the native
    type as well, otherwise it leaks into the JSON payload as a literal NaN.
    """
    import math
    if isinstance(o, dict):
        return {str(k): _safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_safe(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if o is None or isinstance(o, (str, int, bool)):
        return o
    if isinstance(o, float):
        # NaN and +/-Inf are not valid JSON — represent them as null
        return None if (math.isnan(o) or math.isinf(o)) else o
    try:
        import pandas as pd
        if o is pd.NA or (o is not None and pd.isna(o)):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    return str(o)


async def describe(**kwargs) -> dict:
    """
    Compute descriptive statistics for a dataset.

    Args:
        data: list of dicts or dict of columns (or JSON string)
        path: CSV/JSON file path (alternative to data)

    Returns:
        {"ok": True, "describe": {col: {stat: value}}, "shape": [rows, cols]}
    """
    df = load_df(kwargs.get("data"), kwargs.get("path"))
    out = df.describe(include=[np.number])
    return {"ok": True, "describe": _safe(out.to_dict()), "shape": list(df.shape),
            "columns": list(df.columns)}
