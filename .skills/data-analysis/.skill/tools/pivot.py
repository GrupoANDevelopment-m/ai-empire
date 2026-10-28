"""pivot — pivot table."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df
from describe import _safe


async def pivot(**kwargs) -> dict:
    """
    Build a pivot table.

    Args:
        data: dataset
        index: column(s) to index by
        columns: column to pivot on
        values: column to aggregate
        aggfunc: sum|mean|count|median|max|min

    Returns:
        {"ok": True, "shape": [r, c], "result": [...]}
    """
    df = load_df(kwargs.get("data"), kwargs.get("path"))
    idx = kwargs.get("index")
    cols = kwargs.get("columns")
    vals = kwargs.get("values")
    fn = kwargs.get("aggfunc", "sum")
    if not idx or not cols or not vals:
        raise ValueError("index, columns and values are all required")
    out = df.pivot_table(index=idx, columns=cols, values=vals,
                         aggfunc=fn).reset_index()
    out.columns.name = None
    return {"ok": True, "shape": list(out.shape), "result": _safe(out.to_dict(orient="records"))}
