"""run_python — code execution operation."""
import asyncio
from typing import Optional


async def run_python(**kwargs) -> dict:
    """Execute code in sandbox."""
    if "run_python".startswith("run_"):
        code = kwargs.get("code", "")
        return {
            "status": "ok",
            "language": "run_python".replace("run_", ""),
            "stdout": "Mocked output",
            "stderr": "",
            "exit_code": 0,
        }
    return {"status": "ok", "tool": "run_python"}
