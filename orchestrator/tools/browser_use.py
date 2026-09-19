"""Browser-Use wrapper — LLM drives browser (navega, clica, preenche forms)."""
from __future__ import annotations
import httpx
from config import settings


async def browser_search(query: str, num_results: int = 10) -> list[dict]:
    """Pesquisa no Google via browser-use."""
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{settings.browser_use_url}/search",
            json={"query": query, "num_results": num_results},
        )
        r.raise_for_status()
        return r.json().get("results", [])


async def browser_fill_form(url: str, fields: dict[str, str], submit: bool = False) -> dict:
    """Preenche form em uma URL via browser-use."""
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{settings.browser_use_url}/fill-form",
            json={"url": url, "fields": fields, "submit": submit},
        )
        r.raise_for_status()
        return r.json()


async def browser_click(url: str, selector: str | None = None, text: str | None = None) -> dict:
    """Clica em elemento (selector CSS ou texto visível)."""
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{settings.browser_use_url}/click",
            json={"url": url, "selector": selector, "text": text},
        )
        r.raise_for_status()
        return r.json()


async def browser_extract(url: str, prompt: str) -> dict:
    """Extrai dado estruturado de uma página usando LLM."""
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{settings.browser_use_url}/extract",
            json={"url": url, "prompt": prompt},
        )
        r.raise_for_status()
        return r.json()
