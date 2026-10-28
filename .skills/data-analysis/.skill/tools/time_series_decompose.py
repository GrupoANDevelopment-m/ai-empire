"""time_series_decompose — trend/seasonal/residual via moving average."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df
from describe import _safe


async def time_series_decompose(**kwargs) -> dict:
    """
    Decompose a series into trend, seasonal and residual components.

    Args:
        data: dataset
        date_col: datetime column
        value_col: numeric column
        period: seasonal period (default 7)
        path: file path

    Returns:
        {"ok": True, "trend": [...], "seasonal": [...], "residual": [...]}
    """
    import numpy as np
    import pandas as pd
    df = load_df(kwargs.get("data"), kwargs.get("path"))
    dc = kwargs.get("date_col"); vc = kwargs.get("value_col")
    if not dc or not vc:
        raise ValueError("date_col and value_col are required")
    if dc not in df.columns or vc not in df.columns:
        raise ValueError("date_col/value_col not in dataset")

    s = pd.Series(df[vc].to_numpy(float), index=pd.to_datetime(df[dc]))
    s = s.sort_index()
    period = int(kwargs.get("period", 7))
    trend = s.rolling(window=period, center=True, min_periods=1).mean()
    detrended = s - trend
    bucket = pd.Index([t.dayofweek for t in s.index])
    seasonal = detrended.groupby(bucket).transform("mean")
    residual = detrended - seasonal

    return {"ok": True, "period": period, "n": len(s),
            "trend": _safe([round(float(v), 4) for v in trend.fillna(0)]),
            "seasonal": _safe([round(float(v), 4) for v in seasonal.fillna(0)]),
            "residual": _safe([round(float(v), 4) for v in residual.fillna(0)])}
