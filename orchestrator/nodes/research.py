"""Research node — SearXNG + LLM synthesis."""
from state.schema import EmpireState, ResearchNote
from tools.llm import get_llm
from tools.searxng import web_search


async def run(state: EmpireState) -> EmpireState:
    queries = [
        state.goal,
        f"best practices {state.goal}",
        f"competitors {state.goal}",
    ]
    note = ResearchNote(query=state.goal, summary="", sources=[], insights=[])

    for q in queries:
        results = await web_search(q, num_results=5)
        note.sources.extend([r.get("url", "") for r in results if r.get("url")])

    # Summarize with LLM
    llm = get_llm()
    prompt = f"""Resuma os achados da pesquisa sobre '{state.goal}' em 5 bullet points acionáveis.
Fontes: {note.sources[:10]}
"""
    resp = await llm.ainvoke(prompt)
    note.summary = resp.content if hasattr(resp, "content") else str(resp)
    state.research_notes.append(note)
    state.logs.append(f"Research: {len(note.sources)} fontes, summary ok")
    return state
