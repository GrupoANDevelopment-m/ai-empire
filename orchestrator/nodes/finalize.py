"""Finalize — consolida output, fecha state."""
from datetime import datetime
from state.schema import EmpireState


async def run(state: EmpireState) -> EmpireState:
    state.finished_at = datetime.utcnow()
    state.output = {
        "goal": state.goal,
        "leads_found": len(state.leads),
        "leads_qualified": sum(1 for l in state.leads if l.score >= 70),
        "content_generated": len(state.content_queue),
        "content_published": len(state.published),
        "research_notes": len(state.research_notes),
        "duration_seconds": (state.finished_at - state.started_at).total_seconds(),
    }
    state.logs.append(f"✓ Finalizado. {state.output}")
    return state
