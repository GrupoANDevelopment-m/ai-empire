"""correlation — Pearson/Spearman correlation matrix."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df
from describe import _safe


async def correlation(**kwargs) -> dict:
    """
    Compute correlations between numeric columns.

    Args:
        data: dataset
        path: file path
        method: pearson | spearman | kendall (default pearson)
        columns: restrict to these columns

    Returns:
        {"ok": True, "method": str, "matrix": {a: {b: value}}}
    """
    df = load_df(kwargs.get("data"), kwargs.get("path"))
    cols = kwargs.get("columns")
    num = df[cols] if cols else df.select_dtypes(include="number")
    if num.shape[1] < 2:
        raise ValueError("need at least 2 numeric columns")
    m = kwargs.get("method", "pearson")
    mat = num.corr(method=m)
    return {"ok": True, "method": m, "columns": list(num.columns),
            "matrix": _safe(mat.to_dict())}
