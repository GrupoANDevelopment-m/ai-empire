"""
OpenCode Forge — generates tools on-demand using the best LLM available.

The user says: "cria uma ferramenta que calcule meu MRR por cohort"
Forge does:
  1. Reads the request and context (what skills are installed, what data exists)
  2. Picks the best available LLM (anthropic > openai > ollama)
  3. Asks the LLM to generate Python code (run(inputs) -> result)
  4. Validates AST (blocks dangerous calls)
  5. Runs self-test in sandbox
  6. If passes → promotes to .forge/tools/<name>.py
  7. Auto-registers in capability discovery

Each generated tool is versioned and can be rolled back.
"""
import os
import json
import time
import shutil
import hashlib
import asyncio
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from empire.registry.sandbox import (
    validate_ast, run_in_sandbox, SandboxResult, sha256_str, PROFILES,
)


FORGE_DIR = Path(os.getenv("EMPIRE_FORGE_DIR", "/workspace/ai-empire/.forge"))
FORGE_TOOLS_DIR = FORGE_DIR / "tools"
FORGE_REGISTRY = FORGE_DIR / "registry.json"


@dataclass
class GeneratedTool:
    name: str
    code: str
    description: str
    inputs_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    version: int = 1
    created_at: str = ""
    last_invoked: Optional[str] = None
    invoke_count: int = 0
    error_count: int = 0
    model_used: str = ""
    cost_usd: float = 0.0
    enabled: bool = True
    hash: str = ""


# ─── LLM provider ───────────────────────────────────────────────────────────

class LLMProvider:
    """Best-available LLM detection and call."""

    def __init__(self):
        self.providers = []
        self._detect()

    def _detect(self):
        if os.getenv("ANTHROPIC_API_KEY"):
            self.providers.append({
                "name": "anthropic", "priority": 1,
                "model_strong": "claude-sonnet-4-5-20250929",
                "model_cheap": "claude-haiku-4-5-20251001",
                "cost_in_strong": 3.0, "cost_out_strong": 15.0,
                "cost_in_cheap": 0.8, "cost_out_cheap": 4.0,
            })
        if os.getenv("OPENAI_API_KEY"):
            self.providers.append({
                "name": "openai", "priority": 2,
                "model_strong": "gpt-4o",
                "model_cheap": "gpt-4o-mini",
                "cost_in_strong": 5.0, "cost_out_strong": 15.0,
                "cost_in_cheap": 0.15, "cost_out_cheap": 0.6,
            })
        if os.getenv("OLLAMA_URL") or self._check_ollama_local():
            self.providers.append({
                "name": "ollama", "priority": 3,
                "model_strong": "qwen2.5-coder:7b",
                "model_cheap": "qwen2.5:0.5b",
                "cost_in_strong": 0.0, "cost_out_strong": 0.0,
                "cost_in_cheap": 0.0, "cost_out_cheap": 0.0,
            })
        # Sort by priority (lower = better)
        self.providers.sort(key=lambda p: p["priority"])

    def _check_ollama_local(self) -> bool:
        try:
            import urllib.request
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return len(self.providers) > 0

    def best(self, *, complex_task: bool = False) -> Optional[Dict[str, Any]]:
        if not self.providers:
            return None
        p = self.providers[0]
        return {
            **p,
            "model": p["model_strong"] if complex_task else p["model_cheap"],
            "cost_in": p["cost_in_strong"] if complex_task else p["cost_in_cheap"],
            "cost_out": p["cost_out_strong"] if complex_task else p["cost_out_cheap"],
        }

    def list_providers(self) -> List[Dict[str, Any]]:
        return [{"name": p["name"], "priority": p["priority"],
                 "model_strong": p["model_strong"], "model_cheap": p["model_cheap"]}
                for p in self.providers]


async def call_llm(prompt: str, system: str = "", *, max_tokens: int = 4096,
                   complex_task: bool = False) -> Dict[str, Any]:
    """Call the best available LLM. Returns {content, model, cost_usd, provider}."""
    provider = LLMProvider().best(complex_task=complex_task)
    if not provider:
        return {"error": "no LLM provider configured", "content": ""}
    try:
        if provider["name"] == "anthropic":
            return await _call_anthropic(prompt, system, max_tokens, provider)
        elif provider["name"] == "openai":
            return await _call_openai(prompt, system, max_tokens, provider)
        elif provider["name"] == "ollama":
            return await _call_ollama(prompt, system, max_tokens, provider)
    except Exception as e:
        # Try fallback
        all_providers = LLMProvider().providers
        for p in all_providers:
            if p["name"] != provider["name"]:
                try:
                    if p["name"] == "anthropic":
                        return await _call_anthropic(prompt, system, max_tokens, p)
                    elif p["name"] == "openai":
                        return await _call_openai(prompt, system, max_tokens, p)
                    elif p["name"] == "ollama":
                        return await _call_ollama(prompt, system, max_tokens, p)
                except Exception:
                    continue
        return {"error": str(e), "content": ""}


async def _call_anthropic(prompt, system, max_tokens, provider) -> Dict[str, Any]:
    import httpx
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": provider["model"],
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post("https://api.anthropic.com/v1/messages",
                              headers=headers, json=body)
    if r.status_code != 200:
        return {"error": f"anthropic {r.status_code}: {r.text[:200]}", "content": ""}
    data = r.json()
    content = "".join(b.get("text", "") for b in data.get("content", []))
    usage = data.get("usage", {})
    cost = (usage.get("input_tokens", 0) / 1e6 * provider["cost_in"] +
            usage.get("output_tokens", 0) / 1e6 * provider["cost_out"])
    return {
        "content": content,
        "model": provider["model"],
        "provider": "anthropic",
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cost_usd": cost,
    }


async def _call_openai(prompt, system, max_tokens, provider) -> Dict[str, Any]:
    import httpx
    headers = {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": provider["model"], "max_tokens": max_tokens, "messages": messages}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post("https://api.openai.com/v1/chat/completions",
                              headers=headers, json=body)
    if r.status_code != 200:
        return {"error": f"openai {r.status_code}: {r.text[:200]}", "content": ""}
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    cost = (usage.get("prompt_tokens", 0) / 1e6 * provider["cost_in"] +
            usage.get("completion_tokens", 0) / 1e6 * provider["cost_out"])
    return {
        "content": content,
        "model": provider["model"],
        "provider": "openai",
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "cost_usd": cost,
    }


async def _call_ollama(prompt, system, max_tokens, provider) -> Dict[str, Any]:
    import httpx, json
    url = os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/generate"
    full_prompt = (system + "\n\n" if system else "") + prompt
    body = {"model": provider["model"], "prompt": full_prompt, "stream": False}
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(url, json=body)
    if r.status_code != 200:
        return {"error": f"ollama {r.status_code}: {r.text[:200]}", "content": ""}
    data = r.json()
    return {
        "content": data.get("response", ""),
        "model": provider["model"],
        "provider": "ollama",
        "input_tokens": data.get("prompt_eval_count", 0),
        "output_tokens": data.get("eval_count", 0),
        "cost_usd": 0.0,
    }


# ─── Forge ──────────────────────────────────────────────────────────────────

FORGE_SYSTEM_PROMPT = """Você é o OpenCode Forge do AI Empire. Sua tarefa é gerar uma ferramenta Python que será executada num sandbox seguro.

A ferramenta DEVE:
1. Ter uma função `def run(inputs: dict) -> dict` que recebe inputs e retorna resultado
2. NÃO importar módulos proibidos: subprocess, ctypes, socket, threading, pickle, importlib
3. NÃO usar: exec, eval, compile, open() (use apenas leitura de input.json fornecido pelo runner)
4. Ser bem tipada e documentada com docstring
5. Retornar JSON-serializable
6. Tratar erros gracefully com try/except e retornar {"error": "msg"}

Template:
```python
def run(inputs: dict) -> dict:
    \"\"\"Descrição da ferramenta.\"\"\"
    try:
        # lógica aqui
        return {"result": ...}
    except Exception as e:
        return {"error": str(e)}
```

Responda APENAS com o código Python, sem markdown, sem explicações.
"""


class Forge:
    """Generates tools on-demand using LLM."""

    def __init__(self):
        self.tools_dir = FORGE_TOOLS_DIR
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = FORGE_REGISTRY
        self.tools: Dict[str, GeneratedTool] = {}
        self._load_registry()

    def _load_registry(self):
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text())
                for name, entry in data.get("tools", {}).items():
                    code_path = self.tools_dir / f"{name}.py"
                    code = code_path.read_text() if code_path.exists() else ""
                    self.tools[name] = GeneratedTool(**{**entry, "code": code})
            except Exception as e:
                print(f"[forge] failed to load registry: {e}")

    def _save_registry(self):
        data = {"version": 1, "tools": {}}
        for name, tool in self.tools.items():
            entry = asdict(tool)
            entry.pop("code", None)
            data["tools"][name] = entry
        self.registry_path.write_text(json.dumps(data, indent=2, default=str))

    async def generate(self, request: str, context: Dict[str, Any] = None) -> GeneratedTool:
        """Generate a tool from a natural-language request."""
        if not LLMProvider().available:
            raise RuntimeError("no LLM provider configured — set ANTHROPIC_API_KEY, OPENAI_API_KEY, or OLLAMA_URL")
        # Build the prompt with context
        ctx = context or {}
        ctx_str = ""
        if ctx.get("skills"):
            ctx_str += f"\nSkills instaladas: {', '.join(s['name'] for s in ctx['skills'])}\n"
        if ctx.get("mcps"):
            ctx_str += f"\nMCPs ativos: {', '.join(m['name'] for m in ctx['mcps'])}\n"
        if ctx.get("data"):
            ctx_str += f"\nDatasets disponíveis: {', '.join(d['name'] for d in ctx['data'])}\n"

        prompt = f"""Gere uma ferramenta Python para o seguinte pedido:

PEDIDO: {request}

CONTEXTO:{ctx_str}

Requisitos:
- Função def run(inputs: dict) -> dict
- Documentada com docstring
- Sem imports proibidos
- Tratamento de erro

Responda APENAS com o código Python puro (sem ```python```)."""

        result = await call_llm(prompt, FORGE_SYSTEM_PROMPT, max_tokens=3000, complex_task=True)
        if result.get("error"):
            raise RuntimeError(f"LLM error: {result['error']}")

        code = self._extract_code(result["content"])
        tool_name = self._infer_name(request)
        description = request[:200]
        inputs_schema, output_schema = self._infer_schemas(code)

        # AST safety check
        violations = validate_ast(code)
        if violations:
            return GeneratedTool(
                name=tool_name, code=code, description=description,
                inputs_schema=inputs_schema, output_schema=output_schema,
                created_at=datetime.now(timezone.utc).isoformat(),
                model_used=result.get("model", ""),
                cost_usd=result.get("cost_usd", 0),
                hash=sha256_str(code),
            ) if False else None  # Don't save unsafe tools

        # Sandbox self-test
        sb = run_in_sandbox(code, inputs={}, profile=PROFILES["medium"])
        if not sb.success:
            raise RuntimeError(f"sandbox test failed: {sb.stderr[:200]}")

        # Save
        tool = GeneratedTool(
            name=tool_name, code=code, description=description,
            inputs_schema=inputs_schema, output_schema=output_schema,
            created_at=datetime.now(timezone.utc).isoformat(),
            model_used=result.get("model", ""),
            cost_usd=result.get("cost_usd", 0),
            hash=sha256_str(code),
        )
        self.tools[tool_name] = tool
        (self.tools_dir / f"{tool_name}.py").write_text(code)
        self._save_registry()
        return tool

    def _extract_code(self, text: str) -> str:
        """Strip markdown fences if present."""
        text = text.strip()
        if text.startswith("```python"):
            text = text[len("```python"):].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return text

    def _infer_name(self, request: str) -> str:
        """Turn a natural-language request into a snake_case tool name."""
        s = re.sub(r"[^a-zA-Z0-9\s]", "", request.lower())
        words = [w for w in s.split() if len(w) > 2 and w not in {
            "uma", "para", "com", "que", "dos", "das", "por", "sem", "ser", "tem",
            "the", "and", "for", "with", "from", "this", "that", "tool", "create",
        }][:4]
        name = "_".join(words) or "custom_tool"
        name = re.sub(r"[^a-z0-9_]", "", name)
        return name[:50]

    def _infer_schemas(self, code: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Try to extract input/output schemas from the code."""
        # Naive extraction — looks for type hints and docstrings
        inputs_schema = {"type": "object", "properties": {}, "required": []}
        output_schema = {"type": "object", "properties": {}}
        # Look for input access patterns
        for match in re.finditer(r'inputs\.get\(["\'](\w+)["\']\)', code):
            inputs_schema["properties"][match.group(1)] = {"type": "string"}
        # Look for return keys
        for match in re.finditer(r'return\s*\{["\'](\w+)["\']\s*:', code):
            output_schema["properties"][match.group(1)] = {"type": "string"}
        return inputs_schema, output_schema

    def get(self, name: str) -> Optional[GeneratedTool]:
        return self.tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name, "version": t.version,
                "description": t.description,
                "model_used": t.model_used,
                "invoke_count": t.invoke_count,
                "error_count": t.error_count,
                "cost_usd": t.cost_usd,
                "created_at": t.created_at,
                "enabled": t.enabled,
                "hash": t.hash[:20] + "...",
            }
            for t in self.tools.values()
        ]

    def invoke(self, name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke a generated tool in the sandbox."""
        tool = self.tools.get(name)
        if not tool or not tool.enabled:
            raise KeyError(name)
        result = run_in_sandbox(tool.code, inputs=inputs, profile=PROFILES["medium"])
        tool.invoke_count += 1
        if not result.success:
            tool.error_count += 1
        tool.last_invoked = datetime.now(timezone.utc).isoformat()
        self._save_registry()
        return {
            "success": result.success,
            "result": result.stdout,
            "error": result.stderr if not result.success else None,
            "duration_ms": result.duration_ms,
        }

    def rollback(self, name: str, version: int) -> GeneratedTool:
        """Rollback a tool to a previous version."""
        # Simple rollback: re-generate with same name on first call
        raise NotImplementedError("version history not yet implemented")


# ─── Singleton ──────────────────────────────────────────────────────────────

_FORGE: Optional[Forge] = None


def get_forge() -> Forge:
    global _FORGE
    if _FORGE is None:
        _FORGE = Forge()
    return _FORGE
