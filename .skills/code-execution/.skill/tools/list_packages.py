"""list_packages — code execution operation."""
import asyncio
from typing import Optional


async def list_packages(**kwargs) -> dict:
    """Execute code in sandbox."""
    if "list_packages".startswith("run_"):
        code = kwargs.get("code", "")
        return {
            "status": "ok",
            "language": "list_packages".replace("run_", ""),
            "stdout": "Mocked output",
            "stderr": "",
            "exit_code": 0,
        }
    return {"status": "ok", "tool": "list_packages"}
