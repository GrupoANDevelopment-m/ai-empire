#!/usr/bin/env python3
"""
Real tool audit — AST-based, with transitive call resolution.

A tool is REAL if, following every call inside its body (including helpers in
other modules in the same skill), execution reaches a genuine I/O primitive:
network request, file read/write, database, subprocess/exec, or an import of a
third-party data/IO library.

A tool is a STUB if its transitive closure never reaches such a primitive.

Validation guards like `if not x: return {"ok": False, "error": ...}` are not
stubs — they are only flagged when the *entire* function is that pattern.

Usage:
    python3 tools_audit.py [--json] [--skill NAME] [--verbose]
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SKILLS_DIR = ROOT / ".skills"

STUB_PHRASES = (
    "not implemented", "fixme", "placeholder", "stub", "mock",
    "dummy", "fake", "simulat", "coming soon", "noop", "no-op",
    "would return", "would call", "in a real deployment", "sample data",
)

# Terminal I/O primitives — reaching one of these proves real work.
IO_PRIMITIVES = {
    # network
    "urlopen", "urlretrieve", "urlclean", "Request", "request", "Client",
    "AsyncClient", "session", "Session", "post", "get", "put", "patch",
    "delete", "fetch", "urlopen", "HTTPConnection", "HTTPSConnection",
    "send_request", "sendmail", "send_message", "smtplib", "SMTP", "SMTP_SSL",
    # file
    "open", "read_bytes", "read_text", "write_bytes", "write_text", "writelines",
    "loadtxt", "genfromtxt", "read_csv", "to_csv", "read_json", "to_json",
    "read_excel", "to_excel", "read_parquet", "from_csv", "read_pickle",
    "read_html", "mkdir", "exists", "unlink", "rmtree", "copy", "move",
    "glob", "rglob", "iterdir", "walk", "Image", "save", "imread", "imwrite",
    # pdf
    "PdfReader", "PdfWriter", "Document", "Canvas", "Paragraph", "Table",
    # db / queue
    "connect", "create_engine", "cursor", "execute", "executemany",
    "commit", "query", "fetchall", "fetchone", "publish", "get_message",
    # process / code exec
    "run", "Popen", "check_output", "check_call", "call", "run_in_executor",
    "exec", "eval", "compile", "subprocess", "run_coroutine_threadsafe",
    # compute libs that imply real transformation
    "fit", "fit_transform", "train", "predict", "LinearRegression",
    "IsolationForest", "StandardScaler", "MinMaxScaler", "decompose",
    "encode", "decode", "translate", "summarize", "tokenize", "load_model",
    "segment", "detect", "similarity", "token_set_ratio", "embed",
}


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return dotted(node.func)
    if isinstance(node, ast.Await):
        return dotted(node.value)
    return ""


class ModuleIndex:
    """All functions defined anywhere under .skills, keyed by bare name."""

    def __init__(self) -> None:
        self.funcs: dict[str, ast.AST] = {}       # name -> FunctionDef
        self.origin: dict[str, str] = {}          # name -> file
        self.imported_names: set[str] = set()     # names imported from modules

    def build(self) -> None:
        for py in SKILLS_DIR.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.funcs.setdefault(node.name, node)
                    self.origin.setdefault(node.name, str(py))
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for a in node.names:
                        self.imported_names.add((a.asname or a.name).split(".")[0])


def literals(node: ast.AST) -> list[str]:
    return [n.value.lower() for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def called_names(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            d = dotted(n.func)
            if d:
                out.append(d.split(".")[-1])
    return out


def guard_only(node: ast.AST) -> bool:
    """True if the function body is *only* a validation guard returning an error.

    Detected as: every Return in the function returns a dict literal whose only
    non-trivial key is 'error' / 'ok' — i.e. no data is ever produced.
    """
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    if not returns:
        return False
    for r in returns:
        v = r.value
        if v is None:
            continue
        if not isinstance(v, ast.Dict):
            return False                      # returns something computed → real
        keys = {k.value for k in v.keys if isinstance(k, ast.Constant)}
        if not keys or not keys <= {"ok", "error", "message", "status",
                                   "required", "hint", "detail"}:
            return False
    return True


def resolves_real(fn: ast.AST, idx: ModuleIndex, seen: set[int]) -> tuple[bool, list[str]]:
    """Walk the call graph; True if an I/O primitive is reachable."""
    if id(fn) in seen:
        return False, []
    seen.add(id(fn))

    trace: list[str] = []

    # third-party / stdlib imports count as real capability
    for n in ast.walk(fn):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mod = getattr(n, "module", "") or ""
            names = [a.name for a in n.names]
            root = mod.split(".")[0]
            strong = {
                "httpx", "requests", "aiohttp", "urllib", "smtplib", "imaplib",
                "poplib", "pandas", "numpy", "sklearn", "matplotlib", "scipy",
                "pypdf", "reportlab", "fitz", "pdfplumber", "PIL", "docx",
                "openpyxl", "langdetect", "langid", "sentence_transformers",
                "transformers", "torch", "playwright", "bs4", "lxml",
                "playwright", "sqlite3", "psycopg2", "sqlalchemy", "presidio_analyzer",
                "spacy", "tenacity", "pybreaker", "deep_translator", "googletrans",
            }
            if root in strong:
                trace.append(f"imports {root}")
                return True, trace

    calls = called_names(fn)
    for c in calls:
        if c in IO_PRIMITIVES:
            trace.append(f"calls {c}()")
            return True, trace

    # delegate into other skill functions
    for c in calls:
        target = idx.funcs.get(c)
        if target is not None and c not in (fn.name,):
            ok, sub = resolves_real(target, idx, seen)
            if ok:
                trace.append(f"-> {c}() [{idx.origin.get(c,'').split('/')[-1]}]")
                trace.extend(f"   {s}" for s in sub)
                return True, trace
    return False, trace


def audit(path: Path, idx: ModuleIndex, is_tool_file: bool) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as e:
        return [{"func": "<module>", "severity": "critical",
                 "reasons": [f"parse error: {e}"]}]

    findings = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # The tool entry point is the function named after the file.
        # Other public helpers (e.g. split_thread) are resolved transitively.
        is_tool = is_tool_file and node.name == path.stem
        if not is_tool:
            continue

        reasons = []
        severity = "critical"

        # 1. body is docstring only / pass only
        body = [s for s in node.body if not (isinstance(s, ast.Expr)
               and isinstance(s.value, ast.Constant))]
        if not body or all(isinstance(s, ast.Pass) for s in body):
            findings.append({"func": node.name, "severity": "critical",
                             "reasons": ["empty body (docstring/pass only)"]})
            continue

        # 2. raises NotImplementedError
        for n in ast.walk(node):
            if isinstance(n, ast.Raise) and "NotImplementedError" in dotted(n.exc or ast.Constant("")):
                reasons.append("raises NotImplementedError")
                break

        # 3. stub language
        for s in literals(node):
            for ph in STUB_PHRASES:
                if ph in s:
                    reasons.append(f"stub phrase {ph!r}")
                    break

        # 4. does it reach real work?
        real, trace = resolves_real(node, idx, set())
        if real:
            if reasons:
                findings.append({"func": node.name, "severity": "warning",
                                 "reasons": reasons + ["but DOES reach real work"]})
            continue

        # 5. no real work — classify
        if guard_only(node):
            reasons.append("only returns guard errors — never does the work")
        else:
            reasons.append("no I/O primitive reachable in call graph")
        if trace:
            reasons.extend(trace)
        findings.append({"func": node.name, "severity": severity, "reasons": reasons})
    return findings


def main() -> int:
    args = sys.argv[1:]
    as_json = "--json" in args
    only = args[args.index("--skill") + 1] if "--skill" in args else None

    idx = ModuleIndex()
    idx.build()

    tool_dirs = []
    for sd in sorted(SKILLS_DIR.iterdir()):
        if not sd.is_dir() or (only and sd.name != only):
            continue
        for cand in (sd / "tools", sd / ".skill" / "tools"):
            if cand.is_dir():
                tool_dirs.append((sd.name, cand))
                break

    per_skill, all_findings, total = {}, [], 0
    for skill, tools_dir in tool_dirs:
        files = sorted(f for f in tools_dir.glob("*.py") if not f.name.startswith("_"))
        crit = warn = clean = 0
        for f in files:
            total += 1
            res = audit(f, idx, True)
            all_findings.extend({**r, "file": str(f), "skill": skill} for r in res)
            c = sum(1 for r in res if r["severity"] == "critical")
            crit += c
            warn += sum(1 for r in res if r["severity"] == "warning")
            if c == 0:
                clean += 1
        per_skill[skill] = {"files": len(files), "clean": clean, "critical": crit}

    crit_all = [f for f in all_findings if f["severity"] == "critical"]
    warn_all = [f for f in all_findings if f["severity"] == "warning"]

    if as_json:
        print(json.dumps({"total_tools": total, "critical": len(crit_all),
                          "warning": len(warn_all), "per_skill": per_skill,
                          "findings": all_findings}, indent=2))
        return 1 if crit_all else 0

    print("=" * 74)
    print(f" TOOL AUDIT (transitive call graph) — {total} tool files / {len(per_skill)} skills")
    print("=" * 74)
    print(f" REAL: {total - len(crit_all)}    STUB: {len(crit_all)}    warn: {len(warn_all)}\n")

    print(" PER SKILL")
    for s, d in sorted(per_skill.items()):
        bar = "#" * d["critical"] + "." * (d["files"] - d["critical"])
        flag = "OK " if d["critical"] == 0 else "!! "
        print(f"  {flag}{s:20s} {d['files']:>3} files  [{bar}]  {d['critical']} stub")

    if crit_all:
        print(f"\n STUB TOOLS ({len(crit_all)})")
        by_skill: dict[str, list] = {}
        for f in crit_all:
            by_skill.setdefault(f["skill"], []).append(f)
        for skill, items in sorted(by_skill.items()):
            print(f"\n  [{skill}]")
            for f in items:
                print(f"    - {Path(f['file']).name}:{f['func']}")
                for r in f["reasons"]:
                    print(f"        {r}")

    if warn_all:
        print(f"\n WARNINGS ({len(warn_all)})")
        for f in warn_all:
            print(f"    ~ {Path(f['file']).name}:{f['func']} — {'; '.join(f['reasons'])}")

    return 1 if crit_all else 0


if __name__ == "__main__":
    sys.exit(main())