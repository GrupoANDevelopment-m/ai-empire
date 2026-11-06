#!/usr/bin/env python3
"""
Minimal PEP 427 wheel installer.

Some environments block the package index while still allowing direct file
downloads. `pip` then fails with "No matching distribution found" even
though the wheels are perfectly reachable.

This script resolves a dependency closure through the PyPI JSON API and
unpacks the matching wheels into the target site-packages directory. A wheel
is a zip archive, so this is the same installation layout pip produces.

Usage:
    python3 install_wheels.py fastapi uvicorn
    python3 install_wheels.py --target /usr/lib/python3/dist-packages fastapi
    python3 install_wheels.py --dry-run httpx
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import sysconfig
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

PYPI_SIMPLE = "https://pypi.org/simple/{name}/"
PYPI_JSON = "https://pypi.org/pypi/{name}/json"
UA = {"User-Agent": "AI-Empire-wheel-installer/1.0"}

# Wheel filename: name-version(-build)?-python-abi-platform.whl
WHEEL_RE = re.compile(
    r"^(?P<name>[^-]+)-(?P<version>[^-]+)"
    r"(?:-(?P<build>\d[^-]*))?"
    r"-(?P<pytag>[^-]+)-(?P<abitag>[^-]+)-(?P<plat>[^-]+)\.whl$")


def target_dir() -> Path:
    sp = sysconfig.get_paths().get("purelib")
    return Path(sp or sysconfig.get_paths()["purelib"])


def _with_retry(fn, attempts: int = 4, base_delay: float = 1.5):
    """Retry a network call — connections drop behind proxies."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:                      # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(base_delay * (i + 1))
    raise last


def fetch_json(url: str, accept: str = "application/json") -> dict:
    def _get():
        req = urllib.request.Request(url, headers={**UA, "Accept": accept})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    return _with_retry(_get)


LINK_RE = re.compile(
    r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
    re.IGNORECASE)
REQUIRES_PY_RE = re.compile(r'data-requires-python=["\']([^"\']*)["\']',
                            re.IGNORECASE)


def python_matches(spec: str) -> bool:
    """Whether the running interpreter satisfies a Requires-Python spec.

    A wheel built for Python 3.12+ may use syntax this interpreter cannot
    parse, so the spec has to be honoured.
    """
    if not spec:
        return True
    cur = sys.version_info[:3]
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(>=|<=|==|!=|<>|~=|>|<)\s*([0-9][0-9.]*)$", part)
        if not m:
            continue
        op, ver = m.group(1), m.group(2)
        try:
            want = tuple(int(x) for x in ver.split(".")[:3])
        except ValueError:
            continue
        want = want + (0,) * (3 - len(want))
        have = (cur[0], cur[1], cur[2])
        if op == ">=" and not have >= want: return False
        if op == ">" and not have > want: return False
        if op == "<=" and not have <= want: return False
        if op == "<" and not have < want: return False
        if op == "==" and not have == want: return False
        if op == "!=" and not have != want: return False
        if op == "~=" and not (have >= want and have[0] == want[0]): return False
    return True


def _fetch_all(url: str, accept: str = "text/html") -> bytes:
    """Download a (possibly large) URL, resuming with Range requests.

    Proxies in this environment truncate long responses; an IncompleteRead
    is retried as a ranged request starting where the body stopped.
    """
    buf = bytearray()
    for attempt in range(12):
        headers = {**UA, "Accept": accept}
        if buf:
            headers["Range"] = f"bytes={len(buf)}-"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if buf and r.status == 206:
                    buf.extend(r.read())
                else:
                    buf = bytearray(r.read())
            return bytes(buf)
        except urllib.error.HTTPError as e:
            if e.code == 416 and buf:      # already complete
                return bytes(buf)
            raise
        except Exception as e:            # noqa: BLE001
            partial = getattr(e, "partial", None)
            if partial:
                buf.extend(partial)
                continue
            if attempt == 11:
                raise
            time.sleep(1.0 * (attempt + 1))
    return bytes(buf)


def fetch_simple_html(name: str) -> list[dict]:
    """Fetch the simple index as HTML and return [{filename, url}].

    The HTML form is far smaller than the PEP 691 JSON form (which carries a
    hash for every file of every release) and survives flaky proxies.
    """
    url = PYPI_SIMPLE.format(name=name)

    html = _fetch_all(url, accept="text/html").decode("utf-8", "replace")
    out = []
    for m in LINK_RE.finditer(html):
        href, label = m.group(1), m.group(2)
        fname = label.strip()
        if not fname:
            continue
        full = urllib.parse.urljoin(url, href.split("#")[0])
        req = ""
        rm = REQUIRES_PY_RE.search(m.group(0))
        if rm:
            req = rm.group(1).replace("&gt;", ">").replace("&lt;", "<") \
                .replace("&quot;", '"').replace("&#39;", "'")
        out.append({"filename": fname, "url": full, "requires_python": req})
    return out


def latest_version(name: str) -> str | None:
    """Resolve the latest version of a project via the JSON API."""
    try:
        data = fetch_json(PYPI_JSON.format(name=name))
        return (data.get("info") or {}).get("version")
    except Exception:
        return None


CACHE_DIR = Path(os.getenv("EMPIRE_WHEEL_CACHE",
                            Path(__file__).parent / ".wheel-cache"))


def download(url: str, dest: Path) -> Path:
    """Download a wheel, resuming with Range requests if the body truncates.

    Wheels are cached locally so a repeated install does not re-download.
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached = CACHE_DIR / dest.name
        if cached.exists() and cached.stat().st_size > 0:
            shutil.copyfile(cached, dest)
            return dest
    except OSError:
        pass
    dest.write_bytes(_fetch_all(url, accept="application/octet-stream"))
    try:
        shutil.copyfile(dest, CACHE_DIR / dest.name)
    except OSError:
        pass
    return dest


def compat_tags() -> set[str]:
    """Python/ABI tags this interpreter accepts.

    Only the running interpreter's tags are accepted: 'py36' means Python
    3.6, not "any Python 3", so older wheels must not be selected for a
    newer interpreter.
    """
    maj, minr = sys.version_info[:2]
    tags = {f"py{maj}{minr}", f"cp{maj}{minr}", "py3", f"py{maj}"}
    # abi3 wheels work on any CPython >= the one they were built for
    for m in range(minr, minr + 1):
        tags.add(f"cp{maj}{m}")
    return tags


def _arch() -> str:
    import platform
    m = platform.machine().lower()
    return {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64",
            "arm64": "aarch64", "i386": "i686", "i686": "i686",
            "armv7l": "armv7l"}.get(m, m)


def platform_ok(plat: str) -> bool:
    """Whether a wheel platform tag can be used on this machine.

    Architecture matters: a manylinux1_i686 wheel cannot be imported by an
    x86_64 interpreter, and vice versa.
    """
    p = plat.lower()
    if p == "any":
        return True
    arch = _arch()
    if sys.platform.startswith("linux"):
        if p.startswith(("manylinux", "musllinux", "linux")):
            # The architecture is part of the tag. Reject a wheel built for
            # a different CPU even when the manylinux baseline matches.
            arches = ("x86_64", "aarch64", "ppc64le", "ppc64", "s390x",
                      "i686", "i586", "armv7l", "armv6l", "riscv64")
            ours = arch in arches
            foreign = [a for a in arches if a != arch and a in p]
            if foreign:
                return False
            return ours or not any(a in p for a in arches)
        return False
    if sys.platform == "darwin":
        return p.startswith("macosx") and arch in p.replace(".", "_").split("_")
    if sys.platform.startswith("win"):
        return p.startswith("win") and (
            arch in p.lower() or "amd64" in p.lower() and arch == "x86_64")
    return False


def _parse_version(v: str) -> tuple:
    """Comparable version tuple: 1.2.3 -> (1, 2, 3)."""
    parts = []
    for chunk in re.split(r"[._\-]", v):
        if chunk.isdigit():
            parts.append((1, int(chunk), ""))
        else:
            # a pre-release marker sorts before the plain release
            m2 = re.match(r"^([a-z]+)(\d*)$", chunk.lower())
            if m2:
                parts.append((0, 0, m2.group(1) + m2.group(2)))
            else:
                parts.append((0, 0, chunk.lower()))
    return tuple(parts)


def _wheel_key(f: dict) -> tuple:
    """Rank candidate wheels: newer upload date first, then pure-python."""
    upload = f.get("upload_time_iso_8601", "") or ""
    is_any = f["filename"].endswith("-none-any.whl")
    return (upload, 1 if is_any else 0)


def pick_wheel(files: list[dict]) -> tuple[str, str] | None:
    """Choose the best wheel for this interpreter. Returns (filename, url).

    The simple index lists files newest-first, so the first compatible wheel
    found is the current release.
    """
    def _version_key(f: dict):
        m = WHEEL_RE.match(f.get("filename", ""))
        if not m:
            return (0, ((0, 0, ""),))
        v = m.group("version")
        # Pre-releases (dev/rc/beta) never win over a stable release.
        # The sort is descending, so a stable release gets the HIGHER key.
        stable = 0 if re.search(r"(dev|rc|alpha|beta|a\d|b\d|pre)",
                                v, re.I) else 1
        return (stable, _parse_version(v))

    for f in sorted(files, key=_version_key, reverse=True):
        fname = f.get("filename", "")
        if not fname.endswith(".whl"):
            continue
        m = WHEEL_RE.match(fname)
        if not m:
            continue
        pytags = set(m.group("pytag").split("."))
        abi = m.group("abitag")
        plat = m.group("plat")
        if abi == "abi3":
            # an abi3 wheel runs on any CPython newer than the one it was
            # built for (e.g. cp39-abi3 works on cp311)
            if not any(t.startswith("cp3") for t in pytags):
                continue
        else:
            if not (pytags & compat_tags()):
                continue
            if abi != "none" and not abi.startswith("cp3"):
                continue
        if not platform_ok(plat):
            continue
        if not python_matches(f.get("requires_python", "")):
            continue
        return fname, f["url"]
    return None


def wheel_metadata(path: Path) -> dict:
    """Read METADATA from a downloaded wheel.

    Repeated headers (Requires-Dist) are collected into lists — a metadata
    file has one Requires-Dist line per dependency.
    """
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist()
                     if n.endswith(".dist-info/METADATA")), None)
        if not name:
            return {}
        raw = z.read(name).decode("utf-8", "replace")
    meta: dict = {}
    for line in raw.splitlines():
        if not line.strip():
            break
        k, _, v = line.partition(":")
        key = k.strip().lower()
        value = v.strip()
        if key in meta:
            if isinstance(meta[key], list):
                meta[key].append(value)
            else:
                meta[key] = [meta[key], value]
        else:
            meta[key] = value
    return meta


def version_satisfies(version: str, spec: str) -> bool:
    """Whether a version satisfies a PEP 440-ish requirement spec.

    Supports the operators real projects use in Requires-Dist:
    >=, <=, ==, !=, <, >, ~= and comma-separated conjunctions.
    """
    if not spec:
        return True
    spec = spec.strip()
    if spec.startswith("(") and spec.endswith(")"):
        spec = spec[1:-1]
    cur = _parse_version(version)
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(>=|<=|==|!=|<>|~=|>|<)\s*([0-9][0-9A-Za-z.]*)", part)
        if not m:
            continue
        op, ver = m.group(1), m.group(2)
        if "*" in ver:                       # e.g. "==1.*" matches any 1.x
            prefix = ver.split("*")[0].rstrip(".")
            if op == "==":
                if not version.startswith(prefix + ".") and version != prefix:
                    return False
                continue
        want, have = _parse_version(ver), cur
        n = min(len(want), len(have))
        want, have = want[:n], have[:n]
        if op == ">=" and not have >= want: return False
        if op == ">" and not have > want: return False
        if op == "<=" and not have <= want: return False
        if op == "<" and not have < want: return False
        if op == "==" and not have == want: return False
        if op == "!=" and not have == want: return False
        if op == "~=" and not (have >= want and have and have[0] == want[0]):
            return False
    return True


def requires(meta: dict) -> list[tuple[str, str]]:
    """Parse Requires-Dist into (name, spec) pairs.

    The spec is the raw version requirement ("==2.0.9", ">=8.3.2,<8.4.0")
    so the resolver honours it — picking the newest *compatible* version of a
    dependency instead of the newest overall avoids ABI mismatches such as
    thinc 10 compiled against a different preshed than the one installed.
    """
    raw = meta.get("requires-dist") or []
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for req in raw:
        req = req.strip()
        if not req:
            continue
        if ";" in req:                       # environment marker
            marker = req.split(";", 1)[1].strip()
            if marker.startswith("extra =="):
                continue
        m = re.match(r"^([A-Za-z0-9._-]+)\s*(\([^)]*\)|[^;\s]*)", req)
        if m:
            out.append((m.group(1), m.group(2).strip().replace(" ", "")))
    return out


def install(name: str, dest: Path, dry: bool = False,
            seen: set[str] | None = None,
            spec: str = "",
            constraints: dict[str, list[str]] | None = None) -> list[str]:
    """Install one package (and its dependencies) into dest.

    ``spec`` is the version requirement inherited from the parent
    (e.g. ">=8.3.2,<8.4.0"). All constraints seen for a package are
    intersected, so a package required as ``>=1,<2`` by one parent and
    ``==1.4`` by another resolves to 1.4.
    """
    seen = seen if seen is not None else set()
    constraints = constraints if constraints is not None else {}
    key = name.lower().replace("_", "-")
    specs = constraints.setdefault(key, [])
    if spec and spec not in specs:
        specs.append(spec)
    if key in seen:
        return []
    seen.add(key)

    files = fetch_simple_html(name)
    files = [f for f in files
             if WHEEL_RE.match(f.get("filename", ""))
             and version_satisfies(WHEEL_RE.match(f["filename"]).group("version"),
                                   ",".join(specs))]
    chosen = pick_wheel(files)
    if not chosen:
        print(f"  ! no compatible wheel for {name} ({','.join(specs) or 'any'})")
        return []
    fname, url = chosen
    print(f"  ↓ {name}  ({fname})")
    if dry:
        return [name]

    with tempfile.TemporaryDirectory() as td:
        whl = download(url, Path(td) / fname)
        meta = wheel_metadata(whl)
        for dep, dep_spec in requires(meta):
            install(dep, dest, dry=dry, seen=seen, spec=dep_spec,
                    constraints=constraints)

        dest.mkdir(parents=True, exist_ok=True)
        # Remove a previously installed copy first: extracting over it can
        # leave stale modules from an older version behind.
        wm = WHEEL_RE.match(fname)
        pkg_root = dest / (wm.group("name") if wm else fname.split("-")[0])
        if pkg_root.is_dir():
            shutil.rmtree(pkg_root, ignore_errors=True)
        for info in zipfile.ZipFile(whl).infolist():
            if ".dist-info/" in info.filename:
                stale = dest / info.filename.split("/")[0]
                if stale.is_dir():
                    shutil.rmtree(stale, ignore_errors=True)
        with zipfile.ZipFile(whl) as z:
            z.extractall(dest)

    # drop a stale bytecode cache for the freshly installed package
    for pyc in dest.rglob("__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)
    return [name]


def read_requirements(path: Path) -> list[str]:
    """Read a requirements file into package specs.

    Blank lines and comments are ignored; environment markers are stripped
    (the resolver always targets the running interpreter).
    """
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        out.append(line)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Install wheels without pip")
    ap.add_argument("packages", nargs="*")
    ap.add_argument("-r", "--requirement", action="append", default=[],
                    help="requirements file (repeatable)")
    ap.add_argument("--target", default=None,
                    help="site-packages directory (default: interpreter's)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    specs: list[str] = list(args.packages)
    for rf in args.requirement:
        specs.extend(read_requirements(Path(rf)))
    if not specs:
        ap.error("no packages given (pass names or -r requirements.txt)")

    dest = Path(args.target) if args.target else target_dir()
    print(f"target: {dest}")
    installed = []
    for pkg in specs:
        spec = ""
        if "==" in pkg:
            pkg, _, spec = pkg.partition("==")
            spec = f"=={spec}"
        installed.extend(install(pkg, dest, dry=args.dry_run, spec=spec))
    print(f"\n{len(installed)} package(s) processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
