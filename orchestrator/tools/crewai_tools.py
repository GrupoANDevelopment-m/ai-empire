"""CrewAI tools — wrappers para disparar crews."""
from __future__ import annotations
from crews import leads_crew, design_crew, outreach_crew, research_crew


async def run_leads_crew(payload: dict) -> dict:
    return await leads_crew.run(payload)


async def run_design_crew(payload: dict) -> dict:
    return await design_crew.run(payload)


async def run_outreach_crew(payload: dict) -> dict:
    return await outreach_crew.run(payload)


async def run_research_crew(payload: dict) -> dict:
    return await research_crew.run(payload)
