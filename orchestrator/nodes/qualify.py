"""Qualify — LLM scoring de leads (0-100) + tagging."""
from state.schema import EmpireState
from tools.llm import get_llm


async def run(state: EmpireState) -> EmpireState:
    llm = get_llm()
    for lead in state.leads:
        if lead.score > 0:
            continue  # já qualificado
        prompt = f"""Qualifique este lead (0-100, justifique brevemente):

{lead.model_dump_json(indent=2)}

Critérios: fit com ICP, senioridade, urgência, budget sinal.
Responda JSON: {{"score": int, "tags": [str]}}
"""
        resp = await llm.ainvoke(prompt)
        try:
            import json
            data = json.loads(resp.content if hasattr(resp, "content") else "{}")
            lead.score = data.get("score", 50)
            lead.metadata["tags"] = data.get("tags", [])
        except Exception:
            lead.score = 50
    state.leads.sort(key=lambda l: l.score, reverse=True)
    state.logs.append(f"Qualify: {sum(1 for l in state.leads if l.score >= 70)} leads quentes")
    return state
