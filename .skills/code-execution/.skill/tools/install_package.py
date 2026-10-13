"""install_package — code execution operation."""
import asyncio
from typing import Optional


async def install_package(**kwargs) -> dict:
    """Execute code in sandbox."""
    if "install_package".startswith("run_"):
        code = kwargs.get("code", "")
        return {
            "status": "ok",
            "language": "install_package".replace("run_", ""),
            "stdout": "Mocked output",
            "stderr": "",
            "exit_code": 0,
        }
    return {"status": "ok", "tool": "install_package"}
