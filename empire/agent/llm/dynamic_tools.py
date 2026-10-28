"""
Dynamic tool loader — loads tools from ALL .skills/*/tools/*.py at runtime.

Supports TWO patterns:
  Pattern A: `async def tool_name(arg1, arg2, ...)`  (most skills)
  Pattern B: `def run(inputs: dict)`                  (browser-automation, muapi-studio)

Tools are exposed to the LLM via OpenAI-compatible tool definitions.
"""
from __future__ import annotations
import os
import sys
import json
import asyncio
import importlib.util
import inspect
import re
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional

log = logging.getLogger("empire.dynamic_tools")

SKILLS_ROOT = Path(os.getenv("EMPIRE_SKILLS_DIR", "/workspace/ai-empire/.skills"))


def _extract_docstring(doc: str) -> tuple[str, str]:
    """Parse docstring into (summary, detailed_description)."""
    if not doc:
        return ("Tool", "")
    lines = doc.strip().split("\n")
    summary = lines[0].strip()
    detail = "\n".join(lines[1:]).strip()
    return summary, detail


_DOC_FIELD_RE = re.compile(
    r"^\s{4,}([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)\s*:\s*(.*)$")
_DOC_INPUTS_SECTION = re.compile(
    r"^\s*inputs?\s*:\s*$|^\s*Args?\s*:\s*$", re.IGNORECASE)
_DOC_OTHER_SECTION = re.compile(
    r"^\s*(returns?|raises?|yields?|examples?|notes?|attributes)\s*:\s*$",
    re.IGNORECASE)


def _pattern_b_fields_from_doc(doc: str) -> dict[str, dict]:
    """Extract input fields from a Pattern-B docstring.

    Recognises the convention used across the skills:

        inputs:
            prompt (str): required, text description
            seed (int): -1 for random
            wait (bool): if True (default), poll until ready
    """
    fields: dict[str, dict] = {}
    if not doc:
        return fields
    in_section = False
    for raw in doc.split("\n"):
        if _DOC_INPUTS_SECTION.match(raw):
            in_section = True
            continue
        if in_section and _DOC_OTHER_SECTION.match(raw):
            in_section = False
            continue
        if not in_section:
            continue
        m = _DOC_FIELD_RE.match(raw)
        if not m:
            continue
        name, typ, desc = m.group(1), m.group(2).strip(), m.group(3).strip()
        t = typ.lower()
        if t in ("str", "string", "text"):
            jtype = "string"
        elif t in ("int", "integer"):
            jtype = "integer"
        elif t in ("float", "number", "double"):
            jtype = "number"
        elif t in ("bool", "boolean"):
            jtype = "boolean"
        elif t in ("list", "array"):
            jtype = "array"
        elif t in ("dict", "object", "json"):
            jtype = "object"
        else:
            jtype = "string"
        required = bool(re.search(r"\brequired\b", desc, re.I))
        fields[name] = {"type": jtype, "description": desc or name,
                        "required": required}
    return fields


def _pattern_b_fields_from_source(fn: Callable) -> dict[str, dict]:
    """Statically extract the keys a Pattern-B tool reads from `inputs`.

    Browser-automation tools have no docstring, so the only reliable source
    of truth is the code itself: every `inputs.get("key")` / `inputs["key"]`
    is a real input the tool reads.
    """
    import ast
    try:
        src = inspect.getsource(fn)
        tree = ast.parse(src)
    except (OSError, TypeError, SyntaxError, IndentationError):
        return {}
    keys: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == "get"
                and isinstance(f.value, ast.Name) and f.value.id == "inputs"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        k = node.args[0].value
        if not isinstance(k, str) or k in keys:
            continue
        keys[k] = {"type": "string", "description": k, "required": False}
    return keys


def _skill_slug(skill_name: str) -> str:
    """Normalise a skill name for use in a tool name (web-search -> web_search)."""
    return re.sub(r"[^a-z0-9]+", "_", skill_name.lower()).strip("_")


def _func_to_tool_def(fn: Callable, skill_name: str, tool_filename: str) -> dict:
    """Convert a Python function to OpenAI-compatible tool definition.
    
    Handles both patterns:
      - Pattern A: function with named params
      - Pattern B: `def run(inputs: dict)` — single dict param
    """
    sig = inspect.signature(fn)
    doc = inspect.getdoc(fn) or ""
    summary, _ = _extract_docstring(doc)
    
    # Detect Pattern B (run(inputs))
    params = list(sig.parameters.values())
    is_pattern_b = (
        len(params) == 1
        and params[0].name in ("inputs", "input", "data", "payload")
        and params[0].annotation in (inspect.Parameter.empty, dict, "dict")
    )
    
    if is_pattern_b:
        # Pattern B: single `inputs` dict.
        # The tool reads fields from the TOP level of the dict, so the schema
        # must expose the real field names — not a nested "inputs" object.
        fields = _pattern_b_fields_from_doc(doc)
        for k, v in _pattern_b_fields_from_source(fn).items():
            fields.setdefault(k, v)
        props = {k: {"type": v["type"], "description": v["description"]}
                 for k, v in fields.items()}
        schema = {
            "type": "object",
            "properties": props,
            "additionalProperties": True,
        }
        required = [k for k, v in fields.items() if v.get("required")]
        if required:
            schema["required"] = required
        return {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": summary or f"Tool {fn.__name__} from {skill_name}",
                "parameters": schema,
            },
        }
    
    # Detect **kwargs — the tool accepts arbitrary parameters
    has_var_kw = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if has_var_kw:
        return {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": summary or f"Tool {fn.__name__} from {skill_name}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
            },
        }
    
    # Pattern A: standard function with typed parameters
    properties = {}
    required = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        param_type = "string"
        if param.annotation != inspect.Parameter.empty:
            ann = str(param.annotation).lower()
            if "int" in ann:
                param_type = "integer"
            elif "float" in ann or "number" in ann:
                param_type = "number"
            elif "bool" in ann:
                param_type = "boolean"
            elif "list" in ann or "dict" in ann or "any" in ann:
                param_type = "object"
        
        # Try to find description in docstring
        desc = f"Parameter {name}"
        for line in doc.split("\n"):
            if f"{name}:" in line or f"{name} (" in line:
                desc = line.split(":", 1)[1].strip() if ":" in line else desc
                break
        
        properties[name] = {"type": param_type, "description": desc}
        if param.default == inspect.Parameter.empty:
            required.append(name)
    
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    
    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": summary or f"Tool {fn.__name__} from {skill_name}",
            "parameters": schema,
        },
    }


def _find_main_function(module, filename: str) -> Optional[Callable]:
    """Find the main callable in a tool module.
    
    Tries in order:
      1. `async def <filename>(...)` (Pattern A, name matches file)
      2. `def <filename>(...)` (sync, name matches file)
      3. `async def run(inputs)` (Pattern B)
      4. `def run(inputs)` (Pattern B sync)
      5. Any `def main(...)` 
      6. First public function/coroutine in the module
    """
    stem = Path(filename).stem
    
    # Try 1: async def with same name
    for name, obj in inspect.getmembers(module, inspect.iscoroutinefunction):
        if name == stem and obj.__module__ == module.__name__:
            return obj
    
    # Try 2: sync def with same name
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if name == stem and obj.__module__ == module.__name__:
            return obj
    
    # Try 3/4: run(inputs) - either sync or async
    if hasattr(module, "run"):
        return module.run
    
    # Try 5: main
    if hasattr(module, "main"):
        return module.main
    
    # Try 6: first public function defined in this module
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("_") and obj.__module__ == module.__name__:
            return obj
    for name, obj in inspect.getmembers(module, inspect.iscoroutinefunction):
        if not name.startswith("_") and obj.__module__ == module.__name__:
            return obj
    
    return None


def discover_skill_tools() -> dict:
    """
    Walk all .skills/*/ and load their tools/*.py.
    
    Returns:
        {
            "skill_name": {
                "tool_filename_stem": {
                    "module": <module>,
                    "func": <callable>,
                    "tool_def": <openai tool def>,
                    "skill": <skill_name>,
                }
            }
        }
    """
    discovered = {}
    
    if not SKILLS_ROOT.exists():
        log.warning(f"Skills dir does not exist: {SKILLS_ROOT}")
        return discovered
    
    # Skills with explicit per-skill tools/ subdir convention
    for skill_dir in SKILLS_ROOT.iterdir():
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith(".") or skill_dir.name.startswith("__"):
            continue
        
        # Detect tools dir: either <skill>/tools/ or <skill>/.skill/tools/.
        # Both layouts are supported; if a skill has both, load BOTH so no
        # tool is silently dropped.
        _cands = [skill_dir / "tools", skill_dir / ".skill" / "tools"]
        _dirs = [d for d in _cands if d.is_dir()]
        if len(_dirs) > 1:
            log.warning("skill %s has tools in %d locations; loading all of them",
                        skill_dir.name, len(_dirs))
        if not _dirs:
            continue
        
        skill_tools = {}
        _all_files = []
        for _d in _dirs:
            _all_files.extend(sorted(_d.glob("*.py")))
        for tool_file in _all_files:
            if tool_file.name.startswith("_") and tool_file.name != "__init__.py":
                continue
            if tool_file.name == "__init__.py":
                continue
            
            try:
                # Build a unique module name to avoid collisions
                mod_name = f"skill_{skill_dir.name}_{tool_file.stem}"
                spec = importlib.util.spec_from_file_location(mod_name, str(tool_file))
                if spec is None or spec.loader is None:
                    continue
                # Add the tools/ dir to sys.path so `from _http import ...` works
                tools_dir_str = str(tool_file.parent)
                if tools_dir_str not in sys.path:
                    sys.path.insert(0, tools_dir_str)
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                spec.loader.exec_module(module)
                
                func = _find_main_function(module, tool_file.name)
                if func is None:
                    log.debug(f"No main function in {skill_dir.name}/{tool_file.name}")
                    continue
                
                # Use the function's actual name (e.g., "run" for Pattern B, or
                # tool name for Pattern A). The LLM-facing name is namespaced
                # by skill so that tools with the same short name in different
                # skills (extract_text exists in both pdf and web-search)
                # stay distinguishable.
                short_name = func.__name__
                if short_name == "run":
                    short_name = tool_file.stem
                tool_key = short_name
                func_name = f"{_skill_slug(skill_dir.name)}__{short_name}"

                tool_def = _func_to_tool_def(func, skill_dir.name, tool_file.name)
                tool_def["function"]["name"] = func_name
                tool_def["function"].setdefault(
                    "description",
                    f"[{skill_dir.name}] {tool_def['function'].get('description', '')}"
                )
                
                skill_tools[tool_key] = {
                    "module": module,
                    "func": func,
                    "func_name": func_name,
                    "tool_def": tool_def,
                    "skill": skill_dir.name,
                }
            except Exception as e:
                log.debug(f"Failed to load {skill_dir.name}/{tool_file.name}: {e}")
                continue
        
        if skill_tools:
            discovered[skill_dir.name] = skill_tools
    
    return discovered


def all_tool_definitions() -> list[dict]:
    """Return OpenAI-format tool definitions for all skills."""
    discovered = discover_skill_tools()
    defs = []
    for skill_name, tools in discovered.items():
        for tool_name, info in tools.items():
            defs.append(info["tool_def"])
    return defs


def all_tool_names() -> set:
    """Get all available tool names (the names the LLM will see)."""
    discovered = discover_skill_tools()
    names = set()
    for skill_name, tools in discovered.items():
        for tool_name, info in tools.items():
            names.add(info["func_name"])
    return names


def get_skill_for_tool(name: str) -> Optional[str]:
    """Look up which skill owns a given tool name."""
    discovered = discover_skill_tools()
    for skill_name, tools in discovered.items():
        for tool_name, info in tools.items():
            if info["func_name"] == name or tool_name == name:
                return skill_name
    return None


async def execute_skill_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name across all skills.
    
    Pattern A: function(arg1, arg2, ...) — arguments dict is unpacked
    Pattern B: run(inputs) — arguments dict is passed as `inputs`

    Accepts both the namespaced name ("pdf__extract_text") and the bare
    short name ("extract_text"). A bare name that exists in more than one
    skill is ambiguous and is rejected rather than silently resolved to the
    first match.
    """
    discovered = discover_skill_tools()

    # 1) exact namespaced match
    for skill_name, tools in discovered.items():
        for tool_name, info in tools.items():
            if info["func_name"] == name:
                return await _invoke_tool(info, arguments)

    # 2) bare short name — only if unambiguous
    matches = [(skill_name, tool_name, info)
               for skill_name, tools in discovered.items()
               for tool_name, info in tools.items()
               if tool_name == name]
    if len(matches) == 1:
        return await _invoke_tool(matches[0][2], arguments)
    if len(matches) > 1:
        names = ", ".join(sorted(m[2]["func_name"] for m in matches))
        return json.dumps({
            "ok": False,
            "error": f"ambiguous tool name {name!r} — it exists in multiple "
                     f"skills. Use one of: {names}",
        })
    return json.dumps({"ok": False, "error": f"unknown tool: {name}"})


async def _invoke_tool(info: dict, arguments: dict) -> str:
    """Call a discovered tool and serialise the result."""
    func = info["func"]
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    try:
        # Detect Pattern B by looking at the function signature
        is_pattern_b = (
            len(params) == 1
            and params[0].name in ("inputs", "input", "data", "payload")
        )

        if is_pattern_b:
            # The tool reads fields from the TOP level of the dict.
            # Be tolerant: if a caller (or a model trained on the old
            # nested schema) sends {"inputs": {...}}, unwrap it.
            payload = arguments
            if (isinstance(payload, dict)
                    and set(payload.keys()) == {"inputs"}
                    and isinstance(payload.get("inputs"), dict)):
                payload = payload["inputs"]
            if inspect.iscoroutinefunction(func):
                result = await func(payload)
            else:
                result = func(payload)
        else:
            # Detect **kwargs (VAR_KEYWORD) — pass everything through
            has_var_kw = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in params
            )
            if has_var_kw:
                # Function accepts arbitrary kwargs — pass all arguments
                call_args = dict(arguments)
            else:
                # Filter to known params only
                call_args = {
                    p: arguments[p]
                    for p in sig.parameters
                    if p != "self" and p in arguments
                }
            if inspect.iscoroutinefunction(func):
                result = await func(**call_args)
            else:
                result = func(**call_args)

        if not isinstance(result, str):
            result = json.dumps(result, default=str, indent=2)
        return result
    except Exception as e:
        return (f"Error executing {info.get('func_name', '?')}: "
                f"{type(e).__name__}: {e}")


def stats() -> dict:
    """Return stats about the dynamic tool registry."""
    discovered = discover_skill_tools()
    return {
        "skills": len(discovered),
        "tools": sum(len(t) for t in discovered.values()),
        "by_skill": {s: len(t) for s, t in discovered.items()},
    }
