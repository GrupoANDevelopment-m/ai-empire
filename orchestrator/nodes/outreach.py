"""Outreach — CrewAI outreach crew (email + WA + LinkedIn)."""
from state.schema import EmpireState
from tools.crewai_tools import run_outreach_crew


async def run(state: EmpireState) -> EmpireState:
    hot_leads = [l for l in state.leads if l.score >= 70]
    crew_result = await run_outreach_crew({
        "leads": [l.model_dump() for l in hot_leads[:10]],
        "context": [n.summary for n in state.research_notes],
    })
    state.logs.append(f"Outreach: {crew_result.get('contacted', 0)} leads contatados")
    return state
