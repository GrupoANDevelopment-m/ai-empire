"""
Research Crew — watch videos, summarize, extract insights
Agentes:
  - Video Watcher (yt-dlp + Whisper)
  - Insight Extractor (LLM summarize)
  - Trend Reporter (cross-reference + report)
"""
from crewai import Crew, Agent, Task
from tools.llm import get_llm

llm = get_llm(temperature=0.4)

video_watcher = Agent(
    role="Video Watcher",
    goal="Baixar, transcrever e assistir vídeos (YouTube, TikTok, Instagram Reels)",
    backstory="Veterano em conteúdo de vídeo. yt-dlp + Whisper. Resume mesmo vídeos de 1h em 5 bullet points.",
    llm=llm,
    verbose=True,
)

insight_extractor = Agent(
    role="Insight Extractor",
    goal="Extrair insights acionáveis de transcrições",
    backstory="Analista sênior. Acha os 'aha moments' em meio a horas de conteúdo. Categoriza por tema.",
    llm=llm,
    verbose=True,
)

trend_reporter = Agent(
    role="Trend Reporter",
    goal="Cruzar múltiplas fontes e produzir trend report",
    backstory="Ex-analista de tendências. Cross-reference de 10+ fontes. Output é briefing executivo, não livro.",
    llm=llm,
    verbose=True,
)


async def run(payload: dict) -> dict:
    urls = payload.get("urls", [])
    topic = payload.get("topic", "")

    t1 = Task(
        description=f"Para cada URL: {urls}, baixe, transcreva, e resuma em 5 bullet points.",
        agent=video_watcher,
        expected_output="JSON [{url, transcript_summary}]",
    )
    t2 = Task(
        description=f"Extraia insights acionáveis sobre '{topic}' de todas as transcrições.",
        agent=insight_extractor,
        expected_output="Lista de insights categorizados",
        context=[t1],
    )
    t3 = Task(
        description="Produza trend report executivo (1 página) com top 5 oportunidades e bottom 3 riscos.",
        agent=trend_reporter,
        expected_output="Markdown report",
        context=[t2],
    )

    crew = Crew(agents=[video_watcher, insight_extractor, trend_reporter], tasks=[t1, t2, t3], verbose=True)
    result = crew.kickoff()
    return {"report": str(result), "urls_analyzed": len(urls)}
