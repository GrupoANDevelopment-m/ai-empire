"""Shared summarization helpers."""
import sys, os, re
sys.path.insert(0, "/workspace/ai-empire")


async def llm(prompt: str, system: str = None, max_tokens: int = 1024,
              temperature: float = 0.3) -> dict:
    from empire.agent.llm.client import LLMClient
    c = LLMClient()
    if not c.is_available:
        await c.detect()
    if not c.is_available:
        raise RuntimeError(
            "No LLM configured. Set NVIDIA_NIM_API_KEY (free, "
            "https://build.nvidia.com), OPENAI_API_KEY or ANTHROPIC_API_KEY.")
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    r = await c.chat(messages=msgs, temperature=temperature, max_tokens=max_tokens)
    return {"text": (r["choices"][0]["message"]["content"] or "").strip(),
            "model": r.get("model")}


def sentences(text: str) -> list:
    """Split into sentences (handles PT + EN punctuation)."""
    parts = re.split(r'(?<=[.!?…])\s+|\n{2,}', text.strip())
    return [p.strip() for p in parts if p.strip()]


def tokenize(text: str) -> list:
    return re.findall(r"[\wÀ-ÿ']+", text.lower())


STOP = set("""a o e de da do que em um para com nao uma os no se por mais as dos como mas ao
ele das a sua ou quando muito nos ja eu tambem so pelo pela ate isso ela entre depois sem
mesmo aos seus quem nas me esse eles voce essa num nem suas meu as""".split())


def keywords(text: str, top: int = 10) -> list:
    from collections import Counter
    c = Counter(w for w in tokenize(text) if len(w) > 3 and w not in STOP)
    return [w for w, _ in c.most_common(top)]
