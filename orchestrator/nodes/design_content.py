"""Design content — CrewAI design crew + ComfyUI/Penpot."""
from state.schema import EmpireState, ContentItem
from tools.crewai_tools import run_design_crew


async def run(state: EmpireState) -> EmpireState:
    crew_result = await run_design_crew({
        "goal": state.goal,
        "leads": [l.model_dump() for l in state.leads[:5]],
        "research": [n.summary for n in state.research_notes],
    })
    for raw in crew_result.get("content", []):
        state.content_queue.append(ContentItem(**raw))
    state.logs.append(f"Design: {len(state.content_queue)} peças geradas")
    return state
