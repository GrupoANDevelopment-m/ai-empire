"""run_python — execute Python code in a resource-limited subprocess."""
import sys, os, tempfile, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _runner import run


async def run_python(code: str, timeout: int = 30, mem_mb: int = 256,
                     inputs: dict = None) -> dict:
    """
    Run Python source and capture stdout/stderr.

    Args:
        code: Python source to execute
        timeout: seconds before SIGKILL
        mem_mb: memory cap via RLIMIT_AS
        inputs: variables injected as a dict named INPUTS before running

    Returns:
        {"ok": bool, "exit_code": int, "stdout": str, "stderr": str}
    """
    d = tempfile.mkdtemp(prefix="empire_py_")
    path = os.path.join(d, "main.py")
    with open(path, "w") as fh:
        if inputs:
            fh.write(f"INPUTS = {inputs!r}\n")
        fh.write(code)
    rc, out, err = await run([sys.executable, "-I", path], timeout=timeout, cwd=d, mem_mb=mem_mb)
    import shutil; shutil.rmtree(d, ignore_errors=True)
    return {"ok": rc == 0, "exit_code": rc, "stdout": out, "stderr": err,
            "language": "python"}
