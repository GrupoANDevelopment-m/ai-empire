"""run_bash — execute a shell command with resource limits."""
import os, shutil, tempfile, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _runner import run

BLOCKED = ["rm -rf /", ":(){", "mkfs", "dd if=", "> /dev/sd", "shutdown", "reboot",
           "curl | sh", "wget | sh", "chmod -R 777 /", "> /etc/passwd"]


async def run_bash(command: str, timeout: int = 30, mem_mb: int = 256) -> dict:
    """
    Run a shell command.

    Args:
        command: the shell command
        timeout: seconds
        mem_mb: memory cap

    Returns:
        {"ok": bool, "exit_code": int, "stdout": str, "stderr": str}
    """
    for bad in BLOCKED:
        if bad in command:
            raise PermissionError(f"blocked dangerous command fragment: {bad!r}")
    bash = shutil.which("bash") or "/bin/sh"
    d = tempfile.mkdtemp(prefix="empire_sh_")
    rc, out, err = await run([bash, "-c", command], timeout=timeout, cwd=d, mem_mb=mem_mb)
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": rc == 0, "exit_code": rc, "stdout": out, "stderr": err,
            "language": "bash"}
