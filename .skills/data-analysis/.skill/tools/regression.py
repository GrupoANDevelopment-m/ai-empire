"""regression — ordinary least squares via numpy lstsq."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df
from describe import _safe


async def regression(**kwargs) -> dict:
    """
    Fit a linear regression (y on X).

    Args:
        data: dataset
        x: feature column(s) — str or list
        y: target column
        path: file path (alternative to data)

    Returns:
        {"ok": True, "r2": float, "coefficients": {...}, "residuals": float}
    """
    import numpy as np
    df = load_df(kwargs.get("data"), kwargs.get("path"))
    xcols = kwargs.get("x")
    ycol = kwargs.get("y")
    if not xcols or not ycol:
        raise ValueError("x and y are required")
    if isinstance(xcols, str):
        xcols = [xcols]
    for c in xcols + [ycol]:
        if c not in df.columns:
            raise ValueError(f"column not found: {c}")

    sub = df[xcols + [ycol]].dropna()
    if len(sub) < len(xcols) + 2:
        raise ValueError("not enough rows to fit")

    X = np.column_stack([np.ones(len(sub))] + [sub[c].to_numpy(float) for c in xcols])
    y = sub[ycol].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0

    names = ["intercept"] + xcols
    return {"ok": True, "r2": r2, "adj_r2": 1 - (1 - r2) * (len(y) - 1) / (len(y) - len(xcols) - 1),
            "n": len(y),
            "coefficients": _safe(dict(zip(names, beta.tolist()))),
            "residual_std": float(np.std(y - pred))}
