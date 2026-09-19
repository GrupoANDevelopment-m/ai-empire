"""
Outreach Crew — abordagem multi-canal personalizada
Agentes:
  - Email Writer (cold emails)
  - WhatsApp SDR (mensagens curtas, humanizadas)
  - LinkedIn Connector (connection request + DM)
"""
from crewai import Crew, Agent, Task
from tools.llm import get_llm

llm = get_llm(temperature=0.7)

email_writer = Agent(
    role="Email Outreach Specialist",
    goal="Escrever cold emails personalizados com alta taxa de resposta",
    backstory="Veterano de cold email. Sabe que subject > body > CTA. A/B testa tudo. Personaliza pelo menos 3 campos por lead.",
    llm=llm,
    verbose=True,
)

whatsapp_sdr = Agent(
    role="WhatsApp SDR",
    goal="Iniciar conversas WhatsApp naturais e curtas",
    backstory="SDR especializado em WhatsApp Business. Mensagens < 300 chars. Sempre com pergunta aberta no final.",
    llm=llm,
    verbose=True,
)

linkedin_connector = Agent(
    role="LinkedIn Connector",
    goal="Criar connection requests e DMs contextuais",
    backstory="LinkedIn growth expert. Sabe que pedir conexão sem pitch aumenta aceitação em 4x.",
    llm=llm,
    verbose=True,
)


async def run(payload: dict) -> dict:
    leads = payload.get("leads", [])
    context = payload.get("context", [])

    t_email = Task(
        description=f"Para cada lead abaixo, escreva cold email personalizado (subject + body curto, 100-150 palavras). Use o contexto: {context[:2]}. Leads: {leads}",
        agent=email_writer,
        expected_output='JSON [{{"lead_id", "subject", "body"}}]',
    )
    t_wa = Task(
        description=f"Para cada lead, escreva mensagem WhatsApp (< 280 chars, tom humano, pergunta aberta no fim).",
        agent=whatsapp_sdr,
        expected_output='JSON [{{"lead_id", "message"}}]',
    )
    t_li = Task(
        description=f"Para cada lead, escreva connection request LinkedIn (< 300 chars, sem pitch, mencionar contexto comum).",
        agent=linkedin_connector,
        expected_output='JSON [{{"lead_id", "message"}}]',
    )

    crew = Crew(
        agents=[email_writer, whatsapp_sdr, linkedin_connector],
        tasks=[t_email, t_wa, t_li],
        verbose=True,
    )
    result = crew.kickoff()
    return {"contacted": len(leads), "raw": str(result)[:1000]}
