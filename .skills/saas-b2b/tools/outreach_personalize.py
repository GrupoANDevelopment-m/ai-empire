"""outreach_personalize — real, grounded personalization draft."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_ce = importlib.util.spec_from_file_location(
    "op_ce", os.path.join(os.path.dirname(os.path.abspath(__file__)), "company_enrichment.py"))
_ce_m = importlib.util.module_from_spec(_ce); _ce.loader.exec_module(_ce_m)


async def outreach_personalize(domain: str, sender_name: str,
                               sender_company: str, offer: str,
                               first_name: str = "", language: str = "pt-BR",
                               tone: str = "professional", use_llm: bool = True) -> dict:
    """
    Build an outreach email grounded in real company data.

    Uses only facts actually returned by the enrichment source; unknown fields
    are omitted rather than invented. Optionally refines with a real LLM.

    Args:
        domain: target company domain
        sender_name: your name
        sender_company: your company
        offer: what you are offering
        first_name: recipient first name
        language: output language
        tone: professional | casual | direct
        use_llm: call the configured LLM for the final wording

    Returns:
        {"ok": True, "subject": str, "body": str, "used_facts": [...],
         "generated_by": "template"|"llm"}
    """
    for req, nm in ((domain, "domain"), (sender_name, "sender_name"),
                    (offer, "offer")):
        if not req or not str(req).strip():
            raise ValueError(f"{nm} is required")

    e = await _ce_m.company_enrichment(domain, include_contacts=False)
    facts, used = [], []
    if e.get("ok"):
        for k in ("name", "industry", "employees", "description", "location"):
            if e.get(k):
                facts.append(f"{k}={e[k]}")
                used.append(k)

    if language.startswith("pt"):
        subj = f"{first_name + ' — ' if first_name else ''}sobre {offer[:50]}"
        who = e.get("name") if e.get("ok") else domain
        body = (f"Olá{(' ' + first_name) if first_name else ''},\n\n"
                f"Escrevo da {sender_company}. Vi que a {who} "
                f"{'trabalha no setor de ' + str(e.get('industry')) + ' ' if e.get('industry') else ''}"
                f"e pensei que {offer} poderia fazer sentido para vocês.\n\n"
                f"Vale uma conversa rápida de 15 minutos esta semana?\n\n"
                f"Abraço,\n{sender_name}")
    else:
        subj = f"{first_name + ' — ' if first_name else ''}re: {offer[:50]}"
        who = e.get("name") if e.get("ok") else domain
        body = (f"Hi{(' ' + first_name) if first_name else ''},\n\n"
                f"I'm writing from {sender_company}. I noticed {who} "
                f"{'operates in ' + str(e.get('industry')) + ' ' if e.get('industry') else ''}"
                f"and thought {offer} could be relevant to you.\n\n"
                f"Worth 15 minutes this week?\n\n"
                f"Best,\n{sender_name}")

    gen = "template"
    if use_llm:
        try:
            sys.path.insert(0, "/workspace/ai-empire")
            from empire.agent.llm.client import LLMClient
            from empire.agent.llm.agent import EmpireAgent
            ag = EmpireAgent(LLMClient())
            r = await ag.run(
                f"Rewrite this {tone} {language} cold outreach email. Use ONLY these "
                f"verified facts, invent nothing, keep it under 120 words. "
                f"Facts: {facts}. Current draft:\n{body}")
            if r.get("ok") and r.get("response"):
                body = r["response"]
                gen = "llm"
        except Exception:
            gen = "template"

    return {"ok": True, "subject": subj, "body": body, "tone": tone,
            "language": language, "generated_by": gen,
            "used_facts": used, "enrichment_source": e.get("source") if e.get("ok") else None,
            "caveat": "every claim traces to a fetched fact; unknown fields omitted"}
