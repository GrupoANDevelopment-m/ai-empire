"""n8n wrapper — dispara workflows via webhook."""
from __future__ import annotations
import httpx
from config import settings


async def trigger_workflow(workflow: str, data: dict) -> dict:
    """Dispara um workflow n8n via webhook."""
    # n8n webhooks são tipicamente em /webhook/{workflow-id}
    url = f"{settings.n8n_url}/webhook/{workflow}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=data)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e), "workflow": workflow}


async def trigger_publish(content: dict, channels: list[str]) -> dict:
    """Atalho para workflow de publicação multi-canal."""
    return await trigger_workflow("empire-publish", {
        "content": content,
        "channels": channels,
    })
