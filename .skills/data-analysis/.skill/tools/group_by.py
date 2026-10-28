"""group_by — group and aggregate."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df
from describe import _safe


async def group_by(**kwargs) -> dict:
    """
    Group by one or more columns and aggregate.

    Args:
        data: dataset
        by: column name(s) to group by
        agg: dict like {"mrr": "sum"} or a list of aggregations
        path: file path (alternative to data)

    Returns:
        {"ok": True, "groups": int, "result": [...]}
    """
    df = load_df(kwargs.get("data"), kwargs.get("path"))
    by = kwargs.get("by")
    if not by:
        raise ValueError("'by' is required")
    if isinstance(by, str):
        by = [by]
    for c in by:
        if c not in df.columns:
            raise ValueError(f"column not found: {c} (have: {list(df.columns)})")
    agg = kwargs.get("agg") or {"count": "*"}
    if isinstance(agg, dict):
        out = df.groupby(by).agg(agg).reset_index()
    else:
        out = df.groupby(by).agg(agg).reset_index()
    return {"ok": True, "groups": len(out), "by": by, "result": _safe(out.to_dict(orient="records"))}
