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
        # Pattern B: single `inputs` dict
        return {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": summary or f"Tool {fn.__name__} from {skill_name}",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "inputs": {
                            "type": "object",
                            "description": f"Parameters for {fn.__name__}. See docstring for field details.",
                            "additionalProperties": True,
                        }
                    },
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
        
        # Detect tools dir: either <skill>/tools/ or <skill>/.skill/tools/
        if (skill_dir / "tools").is_dir():
            tools_dir = skill_dir / "tools"
        elif (skill_dir / ".skill" / "tools").is_dir():
            tools_dir = skill_dir / ".skill" / "tools"
        else:
            continue
        
        skill_tools = {}
        for tool_file in sorted(tools_dir.glob("*.py")):
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
                
                # Use the function's actual name (e.g., "run" for Pattern B, or tool name for Pattern A)
                # For LLM dispatch, we want a unique name per tool
                func_name = func.__name__
                if func_name == "run":
                    # Pattern B — name by file
                    tool_key = tool_file.stem
                    func_name = tool_key  # rename for LLM clarity
                else:
                    tool_key = func_name
                
                tool_def = _func_to_tool_def(func, skill_dir.name, tool_file.name)
                # Override the function name in the tool def if needed
                if func_name != func.__name__:
                    tool_def["function"]["name"] = func_name
                
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
    """
    discovered = discover_skill_tools()
    
    for skill_name, tools in discovered.items():
        for tool_name, info in tools.items():
            if info["func_name"] == name or tool_name == name:
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
                        if inspect.iscoroutinefunction(func):
                            result = await func(arguments)
                        else:
                            result = func(arguments)
                    else:
                        # Pattern A — filter to known params
                        valid_params = {
                            p for p in sig.parameters
                            if p != "self" and p in arguments
                        }
                        call_args = {k: arguments[k] for k in valid_params}
                        if inspect.iscoroutinefunction(func):
                            result = await func(**call_args)
                        else:
                            result = func(**call_args)
                    
                    if not isinstance(result, str):
                        result = json.dumps(result, default=str, indent=2)
                    return result
                except Exception as e:
                    return f"Error executing {skill_name}.{name}: {type(e).__name__}: {e}"
    
    return f"Tool '{name}' not found. Available tools: {len(all_tool_names())}"


def stats() -> dict:
    """Return stats about the dynamic tool registry."""
    discovered = discover_skill_tools()
    return {
        "skills": len(discovered),
        "tools": sum(len(t) for t in discovered.values()),
        "by_skill": {s: len(t) for s, t in discovered.items()},
    }
