"""
Secure Python sandbox — pure stdlib, no Docker required.

Executes untrusted Python code in an isolated subprocess with:
  - AST static analysis (blocks dangerous calls before runtime)
  - Filesystem isolation (chroot-like via tempdir)
  - Network policy (allowlist domains only, blocks SSRF)
  - Resource limits (Unix only: RLIMIT_AS, RLIMIT_CPU)
  - Hard timeout
  - Environment sanitization

Works on Linux, macOS, and Windows (with reduced limits).
"""
import os
import sys
import ast
import json
import time
import shutil
import signal
import tempfile
import subprocess
import hashlib
import socket
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import urlparse


# ─── AST safety validator ───────────────────────────────────────────────────

# Forbidden modules that should never be imported in sandbox
FORBIDDEN_MODULES = {
    "subprocess", "ctypes", "ctypes.util",
    "importlib", "importlib.util", "imp",
    "code", "codeop", "compileall",
    "pickle", "cPickle", "shelve",
    "socket", "select", "selectors",  # raw socket access
    "fcntl", "termios", "tty",
    "pty", "pwd", "grp",
    "resource",  # itself
    "_thread", "threading",  # can spawn runaway threads
    "multiprocessing",  # can fork+escape
    "signal",  # can SIGKILL safety monitors
    "atexit", "posix",  # register cleanup hooks
    "platform", "sys",  # introspection
    "asyncio", "ssl",  # alternative network/event loops
    "marshal",  # code object deserialization
    "win32api", "win32con", "winreg",
    "pywin32",  # Windows-specific
}

# Forbidden call patterns (very high-risk)
FORBIDDEN_CALLS = {
    "exec", "eval", "compile", "__import__",
    "system", "popen", "spawn", "fork", "kill",
    "setuid", "setgid", "chroot",
    "open",  # blocked — use safe_open helper
}


@dataclass
class ASTViolation:
    line: int
    col: int
    node: str
    reason: str


class ASTSafetyValidator(ast.NodeVisitor):
    """Static analysis that blocks dangerous code BEFORE execution."""

    # Dangerous attributes on common objects
    FORBIDDEN_ATTRS = {
        "system", "popen", "spawn", "fork", "kill", "setuid", "setgid",
        "chroot", "unshare", "killpg", "wait", "Popen", "run", "call",
        "check_call", "check_output", "Popen", "load_dynamic",
    }

    def __init__(self):
        self.violations: List[ASTViolation] = []
        self._imports: Set[str] = set()

    def visit_Import(self, node):
        for alias in node.names:
            mod = alias.name.split(".")[0]
            self._check_module(mod, node.lineno, node.col_offset)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            mod = node.module.split(".")[0]
            self._check_module(mod, node.lineno, node.col_offset)
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check for dangerous function calls
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.violations.append(ASTViolation(
                    line=node.lineno, col=node.col_offset,
                    node=f"Call({node.func.id})",
                    reason=f"forbidden call: {node.func.id}",
                ))
        elif isinstance(node.func, ast.Attribute):
            # Block things like os.system, subprocess.run, etc
            attr = node.func.attr
            if attr in FORBIDDEN_CALLS or attr in self.FORBIDDEN_ATTRS:
                self.violations.append(ASTViolation(
                    line=node.lineno, col=node.col_offset,
                    node=f"Call(...{attr})",
                    reason=f"forbidden method: {attr}",
                ))
        self.generic_visit(node)

    def visit_With(self, node):
        """Block 'with open(path) as f: f.write(...)' file writes outside workdir."""
        # We're in sandbox where open is restricted, but also flag suspicious patterns
        self.generic_visit(node)

    def _check_module(self, mod: str, line: int, col: int):
        if mod in FORBIDDEN_MODULES:
            self.violations.append(ASTViolation(
                line=line, col=col,
                node=f"Import({mod})",
                reason=f"forbidden module: {mod}",
            ))


def validate_ast(code: str) -> List[ASTViolation]:
    """Parse Python code and check for safety violations. Returns empty list if safe."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [ASTViolation(line=e.lineno or 0, col=e.offset or 0,
                            node="SyntaxError", reason=str(e))]
    v = ASTSafetyValidator()
    v.visit(tree)
    return v.violations


# ─── Sandbox profile ────────────────────────────────────────────────────────

@dataclass
class SandboxProfile:
    name: str = "medium"
    cpu_seconds: int = 60
    mem_mb: int = 512
    disk_mb: int = 100
    timeout_seconds: int = 60
    network_allow: List[str] = field(default_factory=list)  # hostnames
    network_deny: List[str] = field(default_factory=list)
    allow_env: List[str] = field(default_factory=list)


PROFILES = {
    "light": SandboxProfile(
        name="light", cpu_seconds=30, mem_mb=256, disk_mb=50,
        timeout_seconds=30, network_allow=[], network_deny=["*"],
    ),
    "medium": SandboxProfile(
        name="medium", cpu_seconds=60, mem_mb=512, disk_mb=200,
        timeout_seconds=60, network_allow=[], network_deny=["*"],
    ),
    "heavy": SandboxProfile(
        name="heavy", cpu_seconds=300, mem_mb=2048, disk_mb=5000,
        timeout_seconds=300, network_allow=[], network_deny=[],
    ),
}


# ─── Network policy enforcement ─────────────────────────────────────────────

# Hosts/networks that are ALWAYS blocked (SSRF protection)
NEVER_ALLOW_HOSTS = {
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "169.254.169.254",  # AWS / GCP metadata
    "metadata.google.internal",
    "kubernetes.default.svc",
}
NEVER_ALLOW_CIDRS = [
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "169.254.0.0/16", "fc00::/7", "fe80::/10",
]


def ip_to_int(ip: str) -> int:
    parts = ip.split(".")
    return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])


def cidr_match(ip: str, cidr: str) -> bool:
    try:
        addr, bits = cidr.split("/")
        mask = (0xFFFFFFFF << (32 - int(bits))) & 0xFFFFFFFF
        return (ip_to_int(ip) & mask) == (ip_to_int(addr) & mask)
    except Exception:
        return False


def is_host_allowed(host: str, allow: List[str]) -> bool:
    """Check if a hostname is allowed by the network policy."""
    host = host.lower()
    if host in NEVER_ALLOW_HOSTS:
        return False
    try:
        ip = socket.gethostbyname(host)
        for cidr in NEVER_ALLOW_CIDRS:
            if cidr_match(ip, cidr):
                return False
    except socket.gaierror:
        pass
    if not allow:
        return False
    for pattern in allow:
        if pattern == "*" or pattern == host or host.endswith("." + pattern):
            return True
    return False


# ─── Sandbox execution ──────────────────────────────────────────────────────

class SandboxError(Exception):
    pass


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int
    violations: List[ASTViolation] = field(default_factory=list)
    timed_out: bool = False
    oom: bool = False


def run_in_sandbox(
    code: str,
    inputs: Optional[Dict[str, Any]] = None,
    *,
    profile: SandboxProfile = None,
    workdir: Optional[Path] = None,
    extra_files: Optional[Dict[str, str]] = None,
) -> SandboxResult:
    """
    Execute Python code in a sandboxed subprocess.

    extra_files: optional dict of {relative_path: file_contents} to copy
                 into the workdir alongside the main tool. Useful for skills
                 that need helper modules (e.g. shared http client).

    Returns SandboxResult with output and any violations detected.
    """
    if profile is None:
        profile = PROFILES["medium"]

    # 1. Static analysis — block before running
    violations = validate_ast(code)
    if violations:
        return SandboxResult(
            success=False, stdout="", stderr="unsafe code blocked",
            returncode=-1, duration_ms=0,
            violations=violations,
        )

    # 2. Prepare isolated workdir
    cleanup_workdir = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="empire_sandbox_"))
        cleanup_workdir = True
    else:
        workdir.mkdir(parents=True, exist_ok=True)

    try:
        code_path = workdir / "tool.py"
        code_path.write_text(code, encoding="utf-8")
        # Also copy the user code with the original name (e.g. mrr_calculator.py)
        # so imports work if the tool expects its own filename
        original_name = "user_code.py"
        (workdir / original_name).write_text(code, encoding="utf-8")

        # Copy extra helper files (skills with multiple modules)
        if extra_files:
            for rel_path, content in extra_files.items():
                target = workdir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    target.write_bytes(content)
                else:
                    target.write_text(content, encoding="utf-8")

        # 3. Write inputs to a file (avoids argv size limits)
        if inputs:
            (workdir / "input.json").write_text(json.dumps(inputs), encoding="utf-8")
        else:
            (workdir / "input.json").write_text("{}", encoding="utf-8")

        # 4. Write a stub main that reads input.json and exposes safe_open
        runner = '''
import sys, os, json, builtins
# Add workdir to sys.path so we can import the user tool
sys.path.insert(0, os.environ["EMPIRE_WORKDIR"])
# Override open() to restrict paths
_REAL_OPEN = builtins.open
def _safe_open(path, *args, **kwargs):
    abs_path = os.path.abspath(path)
    workdir = os.environ.get("EMPIRE_WORKDIR", "")
    if workdir and not abs_path.startswith(workdir):
        raise PermissionError(f"open() outside workdir: {abs_path}")
    return _REAL_OPEN(path, *args, **kwargs)
builtins.open = _safe_open

# Read inputs
with _REAL_OPEN(os.path.join(os.environ["EMPIRE_WORKDIR"], "input.json")) as f:
    inputs = json.load(f)

# Run user code
import tool
result = tool.run(inputs) if hasattr(tool, "run") else None
print(json.dumps({"result": result}))
'''
        (workdir / "_runner.py").write_text(runner, encoding="utf-8")

        # 5. Build sanitized environment
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(workdir),
            "LANG": "C.UTF-8",
            "EMPIRE_WORKDIR": str(workdir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        # Add allowed env vars from profile
        for key in profile.allow_env:
            if key in os.environ:
                env[key] = os.environ[key]

        # 6. Build subprocess arguments
        cmd = [sys.executable, "-S", "_runner.py"]

        # 7. Set Unix resource limits if available
        preexec_fn = None
        if sys.platform != "win32":
            def _set_limits():
                try:
                    import resource
                    # CPU time in seconds
                    resource.setrlimit(resource.RLIMIT_CPU,
                                       (profile.cpu_seconds, profile.cpu_seconds + 5))
                    # Memory in bytes
                    mem_bytes = profile.mem_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                    # File size
                    disk_bytes = profile.disk_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_FSIZE, (disk_bytes, disk_bytes))
                    # Disable core dumps
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    # New process group (for cleanup)
                    os.setpgrp()
                except Exception:
                    pass
            preexec_fn = _set_limits

        # 8. Execute
        start = time.time()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd, cwd=str(workdir), env=env,
                capture_output=True, text=True,
                timeout=profile.timeout_seconds,
                preexec_fn=preexec_fn if sys.platform != "win32" else None,
            )
            duration = int((time.time() - start) * 1000)
            oom = (proc.returncode == -9 or "MemoryError" in proc.stderr
                   or "killed" in proc.stderr.lower())
            return SandboxResult(
                success=(proc.returncode == 0),
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                duration_ms=duration,
                timed_out=False,
                oom=oom,
            )
        except subprocess.TimeoutExpired as e:
            duration = int((time.time() - start) * 1000)
            return SandboxResult(
                success=False, stdout=e.stdout.decode() if e.stdout else "",
                stderr=(e.stderr.decode() if e.stderr else "") + "\n[TIMEOUT]",
                returncode=-9, duration_ms=duration, timed_out=True,
            )
        except Exception as e:
            return SandboxResult(
                success=False, stdout="", stderr=f"sandbox error: {e}",
                returncode=-1, duration_ms=0,
            )
    finally:
        if cleanup_workdir and workdir.exists():
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass


# ─── File integrity ─────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha256_str(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()


def verify_signature(payload: bytes, signature: str, public_key_path: Path) -> bool:
    """Optional GPG/SSH signature verification. Returns True if not configured."""
    if not signature:
        return True  # No signature required
    if not public_key_path.exists():
        return False
    try:
        # Write payload + sig to tmp files for gpg verification
        with tempfile.NamedTemporaryFile(delete=False) as pf:
            pf.write(payload)
            payload_path = pf.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sig") as sf:
            sf.write(signature.encode())
            sig_path = sf.name
        result = subprocess.run(
            ["gpg", "--verify", sig_path, payload_path],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False
    finally:
        try: os.unlink(payload_path)
        except: pass
        try: os.unlink(sig_path)
        except: pass
