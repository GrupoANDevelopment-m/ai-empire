"""load_csv — data analysis operation."""
import json
import asyncio
from typing import Optional, Any
import pandas as pd
import numpy as np


async def load_csv(**kwargs) -> dict:
    """Data analysis operation using pandas/numpy."""
    try:
        if "load_csv" == "load_csv":
            df = pd.read_csv(kwargs["path"])
            return {"rows": len(df), "columns": list(df.columns), "preview": df.head(5).to_dict(orient="records")}
        if "load_csv" == "describe":
            df = pd.DataFrame(kwargs["data"])
            return df.describe().to_dict()
        if "load_csv" == "correlation":
            df = pd.DataFrame(kwargs["data"])
            return df.corr().to_dict()
        # ... more ops
        return {"status": "ok", "tool": "load_csv"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
