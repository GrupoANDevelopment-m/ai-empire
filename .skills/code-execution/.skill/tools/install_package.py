"""install_package — pip install into an isolated venv."""
import os, sys, venv, tempfile, shutil, asyncio


async def install_package(package: str, timeout: int = 180,
                          index_url: str = None) -> dict:
    """
    Install a Python package into a throwaway virtualenv.

    Args:
        package: package specifier e.g. "httpx" or "rich==13.7"
        timeout: seconds
        index_url: optional pip index (e.g. mirror)

    Returns:
        {"ok": bool, "package": str, "version": str, "location": str}
    """
    for bad in (";", "&&", "|", "`", "$("):
        if bad in package:
            raise ValueError(f"unsafe package specifier: {package!r}")
    d = tempfile.mkdtemp(prefix="empire_venv_")
    vp = os.path.join(d, "venv")
    venv.EnvBuilder(with_pip=True, clear=True).create(vp)
    py = os.path.join(vp, "bin", "python")
    cmd = [py, "-m", "pip", "install", "--quiet"]
    if index_url:
        cmd += ["-i", index_url]
    cmd.append(package)

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait()
        shutil.rmtree(d, ignore_errors=True)
        return {"ok": False, "package": package, "error": f"timeout after {timeout}s"}

    ok = proc.returncode == 0
    version = ""
    if ok:
        p2 = await asyncio.create_subprocess_exec(
            py, "-c", f"import importlib.metadata as m;print(m.version({package.split('==')[0].split('>')[0].split('<')[0]!r}))",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        o, _ = await p2.communicate()
        version = o.decode().strip()
    if not ok:
        shutil.rmtree(d, ignore_errors=True)
    return {"ok": ok, "package": package, "version": version,
            "location": None if not ok else vp,
            "stderr": err.decode(errors="replace")[:400] if not ok else ""}
