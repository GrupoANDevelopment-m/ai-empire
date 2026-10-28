"""plot — render a chart to PNG."""
import sys, os, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _data import load_df


async def plot(**kwargs) -> dict:
    """
    Create a matplotlib chart and save it to disk.

    Args:
        data: dataset
        chart: line | bar | scatter | hist | box | pie
        x: x column
        y: y column(s) — list draws multiple series
        title: chart title
        output_path: where to save the PNG

    Returns:
        {"ok": True, "path": str, "bytes": int}
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = load_df(kwargs.get("data"), kwargs.get("path"))
    kind = kwargs.get("chart", "line")
    x = kwargs.get("x")
    y = kwargs.get("y")
    title = kwargs.get("title", f"{kind} chart")
    out = kwargs.get("output_path", f"chart_{kind}.png")

    fig, ax = plt.subplots(figsize=(10, 6))
    ys = y if isinstance(y, list) else ([y] if y else None)

    if kind == "line":
        for col in ys:
            ax.plot(df[x], df[col], label=col, marker="o", markersize=3)
    elif kind == "bar":
        for col in ys:
            ax.bar(df[x], df[col], label=col, alpha=0.8)
    elif kind == "scatter":
        ax.scatter(df[x], df[ys[0]], s=40)
    elif kind == "hist":
        ax.hist(df[ys[0]], bins=30, color="#3b82f6", edgecolor="black")
    elif kind == "box":
        ax.boxplot([df[c].dropna() for c in ys], labels=ys)
    elif kind == "pie":
        ax.pie(df[ys[0]], labels=df[x], autopct="%1.1f%%")
    else:
        raise ValueError(f"unknown chart type: {kind}")

    ax.set_title(title)
    if kind not in ("pie", "hist"):
        ax.set_xlabel(x or "")
        ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)

    size = os.path.getsize(out)
    with open(out, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    return {"ok": True, "path": out, "bytes": size, "chart": kind,
            "base64": b64[:100] + "..." if len(b64) > 100 else b64}
