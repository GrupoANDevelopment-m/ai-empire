"""Shared execution runner with real sandboxing via resource limits."""
import os
import sys
import shutil
import tempfile
import asyncio
from pathlib import Path


def limits(cpu_seconds=10, mem_mb=256, out_mb=16, apply_mem=True):
    """Apply RLIMITs in the child before exec."""
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    if apply_mem:
        b = mem_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        except Exception:
            pass
    resource.setrlimit(resource.RLIMIT_FSIZE, (out_mb * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))


async def run(cmd, timeout=30, cwd=None, env=None, mem_mb=256, apply_mem=True):
    """Run a command with real limits. Returns (rc, stdout, stderr)."""
    def _preexec():
        limits(mem_mb=mem_mb, apply_mem=apply_mem)
    e = dict(os.environ)
    if env:
        e.update(env)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=cwd, env=e, preexec_fn=_preexec,
        )
    except FileNotFoundError:
        raise RuntimeError(f"command not found: {cmd[0]}")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -9, "", f"timeout after {timeout}s"
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")
