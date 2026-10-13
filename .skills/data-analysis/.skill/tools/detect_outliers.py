"""detect_outliers — data analysis operation."""
import json
import asyncio
from typing import Optional, Any
import pandas as pd
import numpy as np


async def detect_outliers(**kwargs) -> dict:
    """Data analysis operation using pandas/numpy."""
    try:
        if "detect_outliers" == "load_csv":
            df = pd.read_csv(kwargs["path"])
            return {"rows": len(df), "columns": list(df.columns), "preview": df.head(5).to_dict(orient="records")}
        if "detect_outliers" == "describe":
            df = pd.DataFrame(kwargs["data"])
            return df.describe().to_dict()
        if "detect_outliers" == "correlation":
            df = pd.DataFrame(kwargs["data"])
            return df.corr().to_dict()
        # ... more ops
        return {"status": "ok", "tool": "detect_outliers"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
