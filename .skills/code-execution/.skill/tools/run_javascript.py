"""run_javascript — execute JS via node with resource limits."""
import os, shutil, tempfile, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _runner import run


async def run_javascript(code: str, timeout: int = 30, mem_mb: int = 256) -> dict:
    """
    Run JavaScript with Node.js.

    Args:
        code: JS source
        timeout: seconds
        mem_mb: memory cap

    Returns:
        {"ok": bool, "exit_code": int, "stdout": str, "stderr": str}
    """
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        raise RuntimeError("node not found. Install Node.js")
    d = tempfile.mkdtemp(prefix="empire_js_")
    path = os.path.join(d, "main.js")
    open(path, "w").write(code)
    # V8 reserves large virtual address space; RLIMIT_AS breaks node at startup.
    # Enforce wall-clock + CPU limits instead.
    rc, out, err = await run([node, path], timeout=timeout, cwd=d, apply_mem=False)
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": rc == 0, "exit_code": rc, "stdout": out, "stderr": err,
            "language": "javascript"}
