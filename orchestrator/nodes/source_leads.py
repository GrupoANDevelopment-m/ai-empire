"""Source leads — CrewAI leads crew + storage no Postgres."""
from state.schema import EmpireState, Lead
from tools.crewai_tools import run_leads_crew


async def run(state: EmpireState) -> EmpireState:
    """Dispara a crew de leads e popula state.leads."""
    crew_result = await run_leads_crew({
        "goal": state.goal,
        "research": [n.summary for n in state.research_notes],
        "limit": 20,
    })
    for raw in crew_result.get("leads", []):
        state.leads.append(Lead(**raw))
    state.logs.append(f"Source leads: {len(state.leads)} encontrados")
    return state
