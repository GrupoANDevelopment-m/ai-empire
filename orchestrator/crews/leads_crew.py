"""
Leads Crew — descobre, enriquece e qualifica leads
Agentes:
  - Scraper (LinkedIn, Maps, Reddit, Quora)
  - Enricher (adiciona emails, telefones, senioridade)
  - Qualifier (LLM scoring)
"""
from crewai import Crew, Agent, Task
from crewai_tools import SerperDevTool, ScrapeWebsiteTool
from tools.llm import get_llm
from tools.searxng import web_search

llm = get_llm(temperature=0.3)

scraper = Agent(
    role="Lead Scraper",
    goal="Encontrar leads qualificados baseando-se no goal do usuário",
    backstory="Especialista em OSINT e lead sourcing. Conhece LinkedIn, Google Maps, Reddit, Quora, diretórios B2B.",
    tools=[ScrapeWebsiteTool()],
    llm=llm,
    verbose=True,
)

enricher = Agent(
    role="Lead Enricher",
    goal="Adicionar emails, telefones e contexto a cada lead",
    backstory="Veterano em enrichment. Usa padrões de email, hunter.io patterns, linkedin scraping.",
    llm=llm,
    verbose=True,
)

qualifier = Agent(
    role="Lead Qualifier",
    goal="Scorar leads de 0-100 baseado em fit com ICP",
    backstory="Ex-BDR, sabe separar 'lead bom' de 'lead frio' em segundos. Justifica cada nota.",
    llm=llm,
    verbose=True,
)


async def run(payload: dict) -> dict:
    goal = payload.get("goal", "")
    limit = payload.get("limit", 10)

    t1 = Task(
        description=f"Encontre {limit} leads potenciais para: {goal}. Retorne nome, empresa, cargo, linkedin, website.",
        agent=scraper,
        expected_output="Lista estruturada em JSON com leads brutos",
    )
    t2 = Task(
        description="Para cada lead, encontre email profissional, telefone, e enriqueça com contexto da empresa (porte, setor).",
        agent=enricher,
        expected_output="JSON com leads enriquecidos",
        context=[t1],
    )
    t3 = Task(
        description="Score cada lead de 0-100 baseado em fit com ICP. Tags: hot, warm, cold. Justifique brevemente.",
        agent=qualifier,
        expected_output='JSON [{"name", "email", "company", "score", "tags", "metadata"}]',
        context=[t2],
    )

    crew = Crew(agents=[scraper, enricher, qualifier], tasks=[t1, t2, t3], verbose=True)
    result = crew.kickoff()

    # Parse output do crew
    import json
    try:
        leads_data = json.loads(str(result))
        if not isinstance(leads_data, list):
            leads_data = leads_data.get("leads", [])
    except Exception:
        leads_data = []

    return {"leads": leads_data, "raw": str(result)[:500]}
