"""Shared translation engine — uses the configured LLM (NVIDIA NIM/OpenAI/etc)."""
import os, sys, asyncio, json

sys.path.insert(0, "/workspace/ai-empire")


async def llm_translate(text: str, target: str, source: str = None) -> dict:
    """Translate via the platform LLM client (real API call)."""
    from empire.agent.llm.client import LLMClient, LLMUnavailable
    c = LLMClient()
    info = await c.detect()
    if not c.is_available:
        raise RuntimeError(
            "No LLM configured. Set NVIDIA_NIM_API_KEY (free, "
            "https://build.nvidia.com), OPENAI_API_KEY or ANTHROPIC_API_KEY.")
    src = f"from {source}" if source and source.lower() != "auto" else ""
    sys_p = (
        f"You are a professional translator. Translate the user's text into "
        f"{target}{src}. Preserve formatting, tone, numbers, and placeholders like "
        f"{{name}}. Return ONLY the translation, no explanation, no quotes."
    )
    r = await c.chat(
        messages=[{"role": "system", "content": sys_p},
                  {"role": "user", "content": text}],
        temperature=0.2,
        max_tokens=4096,
    )
    out = r["choices"][0]["message"]["content"] or ""
    return {"text": out.strip(), "model": r.get("model"),
            "backend": info.get("backend"), "usage": r.get("usage")}
