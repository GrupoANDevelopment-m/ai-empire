"""Human review — pausa o grafo para aprovação humana antes de publish/outreach."""
from state.schema import EmpireState


async def run(state: EmpireState) -> EmpireState:
    """Marca o estado como awaiting_human. LangGraph pausa aqui até resume."""
    state.awaiting_human = True
    state.logs.append("⏸  Aguardando revisão humana. POST /runs/{thread_id}/resume com {approved: bool}")
    return state
