"""detect_outliers — IQR / z-score / isolation-forest."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df
from describe import _safe


async def detect_outliers(**kwargs) -> dict:
    """
    Find outliers in numeric columns.

    Args:
        data: dataset
        columns: columns to check (default: all numeric)
        method: iqr | zscore | isolation
        threshold: iqr multiplier (1.5) or z-score cutoff (3.0)

    Returns:
        {"ok": True, "method": str, "outliers": {col: [indices]}}
    """
    import numpy as np
    df = load_df(kwargs.get("data"), kwargs.get("path"))
    cols = kwargs.get("columns") or list(df.select_dtypes(include="number").columns)
    method = kwargs.get("method", "iqr")
    thr = float(kwargs.get("threshold", 1.5 if method == "iqr" else 3.0))

    result = {}
    for c in cols:
        if c not in df.columns:
            continue
        v = df[c].dropna()
        if v.empty:
            continue
        if method == "iqr":
            q1, q3 = v.quantile(0.25), v.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - thr * iqr, q3 + thr * iqr
            idx = v[(v < lo) | (v > hi)].index.tolist()
        elif method == "zscore":
            mu, sd = v.mean(), v.std()
            if sd == 0:
                idx = []
            else:
                z = (v - mu).abs() / sd
                idx = v[z > thr].index.tolist()
        elif method == "isolation":
            from sklearn.ensemble import IsolationForest
            X = v.to_numpy().reshape(-1, 1)
            pred = IsolationForest(contamination=0.05, random_state=42).fit_predict(X)
            idx = [int(i) for i, p in zip(v.index, pred) if p == -1]
        else:
            raise ValueError(f"unknown method: {method}")
        result[c] = {"count": len(idx), "indices": idx[:50],
                     "values": _safe([float(df.loc[i, c]) for i in idx[:50]])}
    return {"ok": True, "method": method, "threshold": thr, "outliers": result}
