"""run_sql — code execution operation."""
import asyncio
from typing import Optional


async def run_sql(**kwargs) -> dict:
    """Execute code in sandbox."""
    if "run_sql".startswith("run_"):
        code = kwargs.get("code", "")
        return {
            "status": "ok",
            "language": "run_sql".replace("run_", ""),
            "stdout": "Mocked output",
            "stderr": "",
            "exit_code": 0,
        }
    return {"status": "ok", "tool": "run_sql"}
