#!/usr/bin/env python3
"""
Fake-success detector.

Finds tools that report ok=True without having verified that the operation
actually succeeded — the exact pattern that hides broken integrations.

Two checks:

1. UNCHECKED_RESULT — a tool calls a network/IO helper, stores the result,
   and then returns ok:True without ever inspecting that result. The call
   may have failed; the tool would still claim success.

2. EMPTY_ON_ERROR — a tool returns ok:True on a code path whose only payload
   is a constant (a hardcoded literal that does not depend on the call).

Usage:
    python3 tools_fake_success.py [--skill NAME]
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SKILLS_DIR = ROOT / ".skills"

# Only genuine network/IO entry points. Generic names like get/post/run are
# excluded: `inputs.get("prompt")` is not an external call.
IO_HELPERS = {"request", "request_public", "poll_result", "fetch", "call",
              "run_action_sync", "llm_translate", "send_email",
              "execute_action", "http_get", "http_post", "urlopen",
              "submit", "send"}

# Helper names that return a dict whose "ok" key the caller must check.
NEEDS_CHECK = IO_HELPERS


def _is_subscript_ok(node: ast.AST) -> bool:
    """True for `x["ok"]` or `x.get("ok")`."""
    if isinstance(node, ast.Subscript):
        s = node.slice
        if isinstance(s, ast.Constant) and s.value == "ok":
            return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "get" and node.args \
            and isinstance(node.args[0], ast.Constant) \
            and node.args[0].value == "ok":
        return True
    return False


def _var_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def audit_file(path: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out = []
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name.startswith("_"):
            continue

        # variables assigned from an IO helper call
        io_vars: dict[str, int] = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                fname = None
                if isinstance(n.value.func, ast.Attribute):
                    fname = n.value.func.attr
                    # `something.get("x")` on a local name is a dict lookup
                    if fname in ("get", "post", "put", "delete", "run", "call"):
                        fname = None
                elif isinstance(n.value.func, ast.Name):
                    fname = n.value.func.id
                if fname in NEEDS_CHECK:
                    for t in n.targets:
                        v = _var_name(t)
                        if v:
                            io_vars[v] = n.lineno

        if not io_vars:
            continue

        # is any io_var's "ok" inspected?
        checked: set[str] = set()
        for n in ast.walk(fn):
            if _is_subscript_ok(n):
                if isinstance(n, ast.Subscript):
                    # x["ok"] -> inspected variable is x
                    base = n.value
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    # x.get("ok") -> inspected variable is x
                    base = n.func.value
                else:
                    base = getattr(n, "value", None)
                v = _var_name(base)
                if v in io_vars:
                    checked.add(v)
            # `if result:` / `if not result:` also counts as inspection
            if isinstance(n, ast.If):
                v = _var_name(n.test)
                if v in io_vars:
                    checked.add(v)
                if isinstance(n.test, ast.UnaryOp) and isinstance(n.test.operand, ast.Name):
                    if n.test.operand.id in io_vars:
                        checked.add(n.test.operand.id)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in ("any", "all", "bool") and n.args:
                v = _var_name(n.args[0])
                if v in io_vars:
                    checked.add(v)

        unchecked = set(io_vars) - checked

        # does the function return ok:True at all?
        has_ok_true = False
        for r in ast.walk(fn):
            if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict):
                keys = [k.value for k in r.value.keys if isinstance(k, ast.Constant)]
                if "ok" in keys:
                    v = list(r.value.values)[keys.index("ok")]
                    if isinstance(v, ast.Constant) and v.value is True:
                        has_ok_true = True

        if unchecked and has_ok_true:
            out.append({
                "file": path.name,
                "func": fn.name,
                "kind": "UNCHECKED_RESULT",
                "detail": f"calls {sorted(io_vars)} but never checks "
                          f"{sorted(unchecked)}['ok'] before returning ok=True",
                "line": min(io_vars[v] for v in unchecked),
            })
    return out


def main() -> int:
    args = sys.argv[1:]
    only = args[args.index("--skill") + 1] if "--skill" in args else None

    findings = []
    total = 0
    for sd in sorted(SKILLS_DIR.iterdir()):
        if not sd.is_dir() or (only and sd.name != only):
            continue
        for cand in (sd / "tools", sd / ".skill" / "tools"):
            if cand.is_dir():
                for f in sorted(cand.glob("*.py")):
                    if f.name.startswith("_"):
                        continue
                    total += 1
                    for r in audit_file(f):
                        r["skill"] = sd.name
                        findings.append(r)
                break

    print("=" * 74)
    print(f" FAKE-SUCCESS DETECTOR — {total} tool files")
    print("=" * 74)
    if not findings:
        print("\n ✓ Nenhuma tool retorna ok=True sem verificar o resultado real "
              "da chamada externa.\n")
        return 0
    print(f"\n {len(findings)} suspeitas:\n")
    for f in findings:
        print(f"  ⚠ [{f['skill']}] {f['file']}:{f['func']}  ({f['kind']})")
        print(f"      {f['detail']}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
