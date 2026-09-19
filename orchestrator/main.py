"""
AI Empire — LangGraph Orchestrator
Entry point: FastAPI exposing graph endpoints + LangGraph SDK
"""
from __future__ import annotations
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any

from langgraph_sdk import get_client
from langchain.globals import set_llm_cache

from config import settings
from state.schema import EmpireState
from graph.empire_graph import build_empire_graph
from crews import leads_crew, design_crew, outreach_crew, research_crew

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("ai-empire")

# ---- Lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Booting AI Empire orchestrator...")
    log.info(f"  LLM provider: {settings.llm_provider}")
    log.info(f"  Database: {settings.database_url.split('@')[-1]}")
    log.info(f"  Redis: {settings.redis_url}")

    # Compila o grafo principal
    app.state.graph = build_empire_graph()
    log.info("Empire graph compiled ✓")

    yield
    log.info("Shutting down.")


app = FastAPI(
    title="AI Empire",
    description="Orquestrador LangGraph multi-agent local",
    version="1.0.0",
    lifespan=lifespan,
)


# ---- Schemas ----
class RunRequest(BaseModel):
    thread_id: str
    input: dict[str, Any]
    config: dict[str, Any] = {}


class RunResponse(BaseModel):
    thread_id: str
    state: dict[str, Any]
    output: dict[str, Any]


# ---- Health ----
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm": settings.llm_provider,
        "profiles": settings.active_profiles,
    }


# ---- Graph endpoints ----
@app.post("/runs")
async def create_run(req: RunRequest) -> RunResponse:
    """Inicia uma execução do empire graph."""
    try:
        graph = app.state.graph
        result = await graph.ainvoke(req.input, config={"configurable": {"thread_id": req.thread_id}})
        return RunResponse(thread_id=req.thread_id, state=result, output=result.get("output", {}))
    except Exception as e:
        log.exception("Run failed")
        raise HTTPException(500, str(e))


@app.post("/runs/{thread_id}/resume")
async def resume_run(thread_id: str, payload: dict[str, Any]):
    """Retoma uma execução pausada (human-in-the-loop)."""
    graph = app.state.graph
    result = await graph.ainvoke(None, config={"configurable": {"thread_id": thread_id}, **payload})
    return {"thread_id": thread_id, "state": result}


@app.get("/threads/{thread_id}/state")
async def get_state(thread_id: str):
    """Inspeciona o state atual de um thread."""
    graph = app.state.graph
    state = await graph.aget_state(config={"configurable": {"thread_id": thread_id}})
    return state.values if state else {}


# ---- Crew endpoints (sub-orchestration direta) ----
@app.post("/crews/leads")
async def run_leads_crew(payload: dict[str, Any]):
    """Dispara crew de leads."""
    return await leads_crew.run(payload)


@app.post("/crews/design")
async def run_design_crew(payload: dict[str, Any]):
    return await design_crew.run(payload)


@app.post("/crews/outreach")
async def run_outreach_crew(payload: dict[str, Any]):
    return await outreach_crew.run(payload)


@app.post("/crews/research")
async def run_research_crew(payload: dict[str, Any]):
    return await research_crew.run(payload)


# ---- Skills proxy (encaminha para skills Mavis) ----
@app.post("/skills/{skill_name}")
async def invoke_skill(skill_name: str, payload: dict[str, Any]):
    """Invoca uma skill Mavis via HTTP."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"http://skills:9000/{skill_name}", json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(502, f"Skill {skill_name} unreachable: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8123, reload=True)
