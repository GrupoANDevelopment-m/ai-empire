"""run_bash — code execution operation."""
import asyncio
from typing import Optional


async def run_bash(**kwargs) -> dict:
    """Execute code in sandbox."""
    if "run_bash".startswith("run_"):
        code = kwargs.get("code", "")
        return {
            "status": "ok",
            "language": "run_bash".replace("run_", ""),
            "stdout": "Mocked output",
            "stderr": "",
            "exit_code": 0,
        }
    return {"status": "ok", "tool": "run_bash"}
