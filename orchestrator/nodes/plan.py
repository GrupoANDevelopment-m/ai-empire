"""Plan node — LLM decompõe goal em plano estruturado."""
from state.schema import EmpireState
from tools.llm import get_llm


async def run(state: EmpireState) -> EmpireState:
    llm = get_llm()
    prompt = f"""Você é o orquestrador de um sistema multi-agente de marketing e vendas.

Goal do usuário: {state.goal}

Decomponha em um plano estruturado (JSON) com:
- intent (lead_gen | design | publish | research | full_pipeline)
- sub_goals (lista de objetivos menores)
- required_skills (skills Mavis que serão usadas)
- expected_outputs (o que deve ser entregue)

Responda apenas com JSON válido.
"""
    resp = await llm.ainvoke(prompt)
    state.next_action = resp.content if hasattr(resp, "content") else str(resp)
    state.logs.append(f"Plan: {state.next_action[:200]}")
    return state
