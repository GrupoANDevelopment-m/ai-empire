"""
Design Crew — cria copy + assets visuais
Agentes:
  - Copywriter (legendas, títulos, CTAs)
  - Art Director (prompts pra ComfyUI/Fooocus)
  - Visual Producer (executa ComfyUI, edita, exporta)
"""
from crewai import Crew, Agent, Task
from tools.llm import get_llm

llm = get_llm(temperature=0.8)

copywriter = Agent(
    role="Copywriter",
    goal="Escrever copy persuasiva para cada canal (IG, LinkedIn, X, email)",
    backstory="Sênior copywriter de tráfego pago. Conhece hooks, frameworks AIDA/PAS, variação por canal.",
    llm=llm,
    verbose=True,
)

art_director = Agent(
    role="Art Director",
    goal="Criar prompts para gerar visuais (ComfyUI/Fooocus/SDXL/FLUX)",
    backstory="Diretor de arte digital, fluent em Stable Diffusion, FLUX, ControlNet. Prompt engineer sênior.",
    llm=llm,
    verbose=True,
)

visual_producer = Agent(
    role="Visual Producer",
    goal="Disparar ComfyUI/Fooocus pra gerar imagens, retornar URLs",
    backstory="Produtor de assets visuais. Conhece aspect ratios, seeds, negative prompts, upscaling.",
    llm=llm,
    verbose=True,
)


async def run(payload: dict) -> dict:
    goal = payload.get("goal", "")
    leads = payload.get("leads", [])

    t1 = Task(
        description=f"Crie 5 peças de conteúdo (IG post, LinkedIn carousel, tweet thread, email subject+body) sobre: {goal}. Audience: {leads[:2]}",
        agent=copywriter,
        expected_output="JSON com array de content items: {kind, title, body, channels}",
    )
    t2 = Task(
        description="Para cada peça, gere prompt de imagem (FLUX/SDXL) e spec visual (aspect ratio, mood, colors).",
        agent=art_director,
        expected_output="JSON com prompts por peça",
        context=[t1],
    )
    t3 = Task(
        description="Liste o que precisa ser gerado pelo ComfyUI e retorne URLs mockadas (será integrado depois).",
        agent=visual_producer,
        expected_output="JSON com media_url por content",
        context=[t2],
    )

    crew = Crew(agents=[copywriter, art_director, visual_producer], tasks=[t1, t2, t3], verbose=True)
    result = crew.kickoff()

    import json
    try:
        data = json.loads(str(result))
    except Exception:
        data = {"raw": str(result)[:1000]}

    return data
