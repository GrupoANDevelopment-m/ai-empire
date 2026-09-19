"""
Empire Agent — natural language interface to all skills.
Parses user intent, dispatches to the right skill, returns natural language result.
"""
from __future__ import annotations
import re
import json
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from enum import Enum

log = logging.getLogger("empire.agent")

# ---- Intent taxonomy ----
# Each intent maps to a skill + action.
# We use pattern matching for now; could swap for an LLM classifier later.

INTENT_PATTERNS = [
    # Lead sourcing
    (r"(?i)\b(find|get|source|search|scrape).*(lead|prospect|contact)", "lead_sourcing"),
    (r"(?i)\b(10|20|50|100)\s+(\w+).*in\s+(\w+)", "lead_sourcing"),  # "10 SaaS in Brazil"

    # Lead qualification
    (r"(?i)\b(qualify|score|rank|triage).*(lead|prospect)", "lead_qualification"),
    (r"(?i)\bhow\s+hot\s+is\s+(this|the)", "lead_qualification"),

    # Outreach
    (r"(?i)\b(send|write|draft|compose).*(email|outreach)", "outreach_email"),
    (r"(?i)\bcold\s+email", "outreach_email"),
    (r"(?i)\b(whatsapp|wa)\s+(message|msg|outreach)", "outreach_whatsapp"),
    (r"(?i)\blinkedin.*(connect|message|dm|outreach)", "outreach_linkedin"),

    # Design
    (r"(?i)\b(generate|create|make|design|draw).*(image|picture|illustration|banner|thumbnail|logo|post|cover)", "design_image"),
    (r"(?i)\b(generate|create|make).*(video|reel|short|clip)", "design_video"),

    # Publishing
    (r"(?i)\b(post|publish|share|upload).*(social|twitter|x|linkedin|instagram|facebook|telegram|reddit)", "publishing_social"),
    (r"(?i)\bschedule\s+(a\s+)?post", "publishing_social"),

    # Browser
    (r"(?i)\b(go\s+to|open|visit|navigate|browse).*(website|url|page|site)", "browser_automation"),
    (r"(?i)\b(fill|submit|complete).*(form|signup|registration)", "browser_automation"),
    (r"(?i)\b(search|google)\s+for\s+", "browser_automation"),
    (r"(?i)\bclick\s+(on\s+)?", "browser_automation"),
    (r"(?i)\bextract\s+(data|info|prices?|emails?)", "browser_automation"),

    # Video research
    (r"(?i)\b(watch|summarize|transcribe).*(video|youtube|reel|tiktok|podcast)", "video_research"),
    (r"(?i)\bwhat\s+do\s+(people|they|videos?).*say\s+about", "video_research"),

    # Lead pipeline
    (r"(?i)\b(run|start|launch|execute).*(campaign|pipeline|sequence)", "lead_pipeline"),
    (r"(?i)\bbook\s+(\d+)\s+demo", "lead_pipeline"),

    # Inbox
    (r"(?i)\b(reply|respond|answer).*(message|email|dm)", "inbox_management"),
    (r"(?i)\bcheck\s+(my\s+)?(inbox|conversations)", "inbox_management"),

    # Test commands
    (r"(?i)\btest\s+(the\s+)?(browser|lead|design|outreach|publishing|all|everything|circuit|breaker|retry|fallback|healing|learning|failover|self)", "test_natural"),
    (r"(?i)\b(run|execute)\s+(the\s+)?test", "test_natural"),
    (r"(?i)\b(run|execute)\s+test", "test_natural"),

    # Health / status
    (r"(?i)\b(health|status|how\s+is|are\s+you\s+ok|are\s+things\s+up)", "health_check"),
    (r"(?i)\bwhat'?s\s+up", "health_check"),
    (r"(?i)\bshow\s+(me\s+)?(skills|capabilities|what\s+you\s+can\s+do)", "list_skills"),
    (r"(?i)\bhelp", "list_skills"),

    # Conversational
    (r"(?i)^(hi|hello|hey|oi|olá|hola|bonjour)\b", "greeting"),
    (r"(?i)\b(thanks|thank\s+you|obrigad[oa]|merci|gracias)\b", "thanks"),
    (r"(?i)\b(bye|exit|quit|goodbye|tchau|adios)\b", "exit"),
]


@dataclass
class AgentContext:
    """Per-conversation state — remembers leads, threads, history."""
    history: list[dict] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    thread_id: str = "default"

    def remember(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)


class Agent:
    """
    Natural-language interface to all AI Empire skills.
    Parses intent, dispatches to skill, returns human-readable result.

    Usage:
        agent = Agent()
        result = await agent.handle("find me 10 SaaS CTOs in Brazil")
        print(result.text)
    """

    def __init__(self, gateway_url: str = "http://localhost:8123"):
        self.gateway_url = gateway_url
        self.skills = self._discover_skills()

    def _discover_skills(self) -> dict[str, str]:
        """Load available skills from /workspace/.skills/."""
        from pathlib import Path
        skills = {}
        skills_dir = Path("/workspace/.skills")
        if not skills_dir.exists():
            return skills
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            md = skill_dir / "SKILL.md"
            if md.exists():
                text = md.read_text()
                # Parse YAML frontmatter (between two --- markers)
                desc = ""
                if text.startswith("---"):
                    try:
                        end = text.index("\n---", 3)
                        fm = text[3:end]
                        for line in fm.split("\n"):
                            if line.startswith("description:"):
                                desc = line[len("description:"):].strip()
                                if desc.startswith('"') and desc.endswith('"'):
                                    desc = desc[1:-1]
                                elif desc.startswith("'") and desc.endswith("'"):
                                    desc = desc[1:-1]
                                break
                    except ValueError:
                        pass
                skills[skill_dir.name] = desc or "(no description)"
        return skills

    def detect_intent(self, text: str) -> tuple[str, dict]:
        """
        Detect which skill the user wants to invoke.
        Returns (intent_name, extracted_params).
        """
        text_lower = text.lower().strip()

        # 1. Pattern match
        for pattern, intent in INTENT_PATTERNS:
            if re.search(pattern, text):
                params = self._extract_params(text, intent)
                return intent, params

        # 2. Fallback: treat as a general lead pipeline goal
        return "general_goal", {"text": text}

    def _extract_params(self, text: str, intent: str) -> dict:
        """Pull out structured parameters from the natural language text."""
        params: dict[str, Any] = {"text": text}

        # Numbers (quantity)
        m = re.search(r"\b(\d+)\b", text)
        if m:
            params["limit"] = int(m.group(1))

        # Geo: "in Brazil", "in São Paulo", "in France"
        geo_match = re.search(r"\bin\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)", text)
        if geo_match:
            params["geo"] = geo_match.group(1)

        # Industry: "SaaS", "Fintech", etc.
        industries = ["saas", "fintech", "ecommerce", "e-commerce", "healthcare", "edtech",
                      "ai", "ml", "crypto", "consulting", "marketing", "manufacturing"]
        for ind in industries:
            if ind in text.lower():
                params["industry"] = ind
                break

        # Seniority
        seniority_map = {
            "cto": ["cto", "chief technology"],
            "ceo": ["ceo", "chief executive"],
            "vp": ["vp", "vice president"],
            "director": ["director", "head of"],
            "manager": ["manager"],
        }
        text_lower = text.lower()
        for level, keywords in seniority_map.items():
            for kw in keywords:
                if kw in text_lower:
                    params["seniority"] = level
                    break
            if "seniority" in params:
                break

        # URLs
        url_match = re.search(r"https?://\S+", text)
        if url_match:
            params["url"] = url_match.group(0)

        return params

    async def handle(self, text: str, ctx: AgentContext | None = None) -> dict:
        """
        Handle a user message.
        Returns {text: str, intent: str, params: dict, data?: Any}
        """
        if ctx is None:
            ctx = AgentContext()

        intent, params = self.detect_intent(text)

        # Save to history
        ctx.history.append({"role": "user", "text": text, "intent": intent})

        # Route
        if intent == "greeting":
            return self._respond("Hey! 👑 I'm the AI Empire agent. Tell me what to do — find leads, send emails, generate designs, run campaigns... or just say 'help' to see everything I can do.", intent, params)

        if intent == "thanks":
            return self._respond("Anytime. What else?", intent, params)

        if intent == "exit":
            return self._respond("Bye! 👋 Run `./empire` anytime to come back.", intent, params)

        if intent == "list_skills":
            return self._list_skills(intent, params)

        if intent == "health_check":
            return await self._health_check(intent, params)

        if intent == "test_natural":
            return await self._test_natural(text, intent, params)

        # Skills that need backend (graceful if not running)
        if intent in ("lead_sourcing", "lead_qualification", "lead_pipeline"):
            return await self._handle_lead(intent, params, ctx)

        if intent in ("outreach_email", "outreach_whatsapp", "outreach_linkedin"):
            return await self._handle_outreach(intent, params, ctx)

        if intent in ("design_image", "design_video"):
            return await self._handle_design(intent, params, ctx)

        if intent in ("publishing_social",):
            return await self._handle_publishing(intent, params, ctx)

        if intent == "browser_automation":
            return await self._handle_browser(params, ctx)

        if intent == "video_research":
            return await self._handle_video_research(params, ctx)

        if intent == "inbox_management":
            return await self._handle_inbox(params, ctx)

        # Default
        return self._respond(
            f"Hmm, I'm not 100% sure what you mean by that. Try something like:\n"
            f"  • 'find me 20 SaaS CTOs in Brazil'\n"
            f"  • 'send a cold email to <name>'\n"
            f"  • 'generate an Instagram post about <topic>'\n"
            f"  • 'test the browser'\n"
            f"  • 'help' to see everything",
            intent, params,
        )

    def _respond(self, text: str, intent: str, params: dict, data: Any = None) -> dict:
        return {"text": text, "intent": intent, "params": params, "data": data}

    def _list_skills(self, intent: str, params: dict) -> dict:
        skills_by_cat = {
            "🎯 Lead generation": ["lead-sourcing", "lead-qualification", "lead-pipeline"],
            "📧 Outreach": ["outreach-email", "outreach-whatsapp", "outreach-linkedin"],
            "🎨 Design": ["design-image", "design-video"],
            "🌐 Browser & research": ["browser-automation", "video-research"],
            "📢 Publishing": ["publishing-social"],
            "💬 Conversations": ["inbox-management", "client-approach"],
            "⚙️  Infrastructure": ["ai-gateway", "self-healing", "self-learning", "failover"],
        }
        lines = ["Here's what I can do, in plain language:\n"]
        for cat, skills in skills_by_cat.items():
            lines.append(f"**{cat}**")
            for s in skills:
                desc = self.skills.get(s, "—")
                # Trim description to first 100 chars
                desc_short = (desc[:120] + "…") if len(desc) > 120 else desc
                lines.append(f"  • `{s}` — {desc_short}")
            lines.append("")
        lines.append("Just talk to me. Examples:")
        lines.append("  • \"find 10 SaaS CTOs in Brazil\"")
        lines.append("  • \"send a cold email to that lead\"")
        lines.append("  • \"generate an Instagram post about AI agents\"")
        lines.append("  • \"watch this video and tell me what they say about pricing\"")
        lines.append("  • \"test the browser\" / \"test all\"")
        return self._respond("\n".join(lines), intent, params)

    async def _health_check(self, intent: str, params: dict) -> dict:
        import httpx
        results = []
        services = [
            ("LangGraph (orchestrator)", f"{self.gateway_url}/health"),
            ("Ollama (local LLM)", "http://localhost:11434/api/tags"),
            ("Open WebUI (chat)", "http://localhost:3000"),
            ("n8n (workflows)", "http://localhost:5678"),
            ("ComfyUI (images)", "http://localhost:8188"),
            ("Penpot (design)", "http://localhost:9001"),
        ]
        async with httpx.AsyncClient(timeout=2) as client:
            for name, url in services:
                try:
                    r = await client.get(url)
                    status = "✅ up" if r.status_code in (200, 204) else f"⚠️  {r.status_code}"
                except Exception as e:
                    status = f"❌ down ({type(e).__name__})"
                results.append(f"  {status}  {name}")
        return self._respond(
            "Here's the health of your empire:\n\n" + "\n".join(results) +
            "\n\nTo start missing services: `./empire start` or `docker compose --profile <name> up -d`",
            intent, params,
        )

    async def _test_natural(self, text: str, intent: str, params: dict) -> dict:
        """Map natural language to test suite and run it."""
        from empire.nl.test_runner import NLTestRunner
        runner = NLTestRunner()
        result = await runner.run_from_text(text)
        return self._respond(result["text"], intent, params, data=result)

    # ---- Skill handlers (these talk to the actual services) ----
    async def _handle_lead(self, intent: str, params: dict, ctx: AgentContext) -> dict:
        import httpx
        limit = params.get("limit", 20)
        goal = params.get("text", "")
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                r = await client.post(
                    f"{self.gateway_url}/crews/leads",
                    json={"goal": goal, "limit": limit, **params},
                )
                r.raise_for_status()
                data = r.json()
                leads = data.get("leads", [])
                ctx.remember("last_leads", leads)
                if not leads:
                    return self._respond(
                        f"Couldn't find leads matching '{goal}'. Try being more specific (industry, role, geo).",
                        intent, params,
                    )
                # Format the leads nicely
                lines = [f"Found {len(leads)} leads:\n"]
                for i, lead in enumerate(leads[:10], 1):
                    name = lead.get("name", "?")
                    company = lead.get("company", "?")
                    role = lead.get("role", "?")
                    score = lead.get("score", "?")
                    email = lead.get("email", "no email")
                    lines.append(f"  {i}. **{name}** — {role} at {company} (score {score})")
                    lines.append(f"     {email}")
                if len(leads) > 10:
                    lines.append(f"  …and {len(leads) - 10} more")
                lines.append(f"\nNext: 'send cold email to #1' or 'qualify these leads'")
                return self._respond("\n".join(lines), intent, params, data={"leads": leads})
            except Exception as e:
                return self._respond(
                    f"Heads up: lead service isn't reachable ({e}). "
                    f"Start it with: `./empire start leads` or `docker compose --profile leads up -d`",
                    intent, params,
                )

    async def _handle_outreach(self, intent: str, params: dict, ctx: AgentContext) -> dict:
        leads = ctx.recall("last_leads", [])
        if not leads:
            return self._respond(
                "I don't have any leads to contact yet. Find some first: 'find me 10 SaaS CTOs in Brazil'",
                intent, params,
            )
        # Take first lead (or specific index)
        target = leads[0]
        return self._respond(
            f"📧 Drafting cold email for **{target.get('name')}** ({target.get('company')})…\n\n"
            f"Subject: Quick question about {target.get('company')}'s growth\n\n"
            f"Hi {target.get('name', 'there')},\n\n"
            f"I noticed {target.get('company')} is scaling — congrats on the momentum.\n"
            f"I work with similar {params.get('industry', 'companies')} and have a few ideas that could save your team 10+ hours/week.\n\n"
            f"Open to a 15-min call this week?\n\n"
            f"— Mavis",
            intent, params, data={"draft": True, "lead": target},
        )

    async def _handle_design(self, intent: str, params: dict, ctx: AgentContext) -> dict:
        kind = "image" if intent == "design_image" else "video"
        prompt = params.get("text", "abstract design").replace("generate", "").replace("create", "").replace("make", "").strip()
        return self._respond(
            f"🎨 Generating {kind} for: *\"{prompt}\"*\n\n"
            f"With ComfyUI/FLUX (or Fooocus/SDXL), I'd render at 1024x1024 for image, "
            f"or 16:9 4s for video.\n\n"
            f"Note: full generation needs the design profile running. "
            f"Start it with: `./empire start design`\n\n"
            f"Once running, this command will return the actual file URL.",
            intent, params, data={"prompt": prompt, "kind": kind},
        )

    async def _handle_publishing(self, intent: str, params: dict, ctx: AgentContext) -> dict:
        return self._respond(
            f"📢 To publish, I need the content + channels. Try:\n"
            f"  • 'post \"<text>\" to twitter and linkedin'\n"
            f"  • 'schedule an Instagram post for tomorrow 9am'\n\n"
            f"This goes through n8n. Start it: `./empire start core`",
            intent, params,
        )

    async def _handle_browser(self, params: dict, ctx: AgentContext) -> dict:
        url = params.get("url", "")
        if url:
            return self._respond(
                f"🌐 Going to {url} via browser-use…\n\n"
                f"Browser service needs to be running: `./empire start browser`\n\n"
                f"Once up, I'll navigate, fill forms, click buttons — whatever you need.",
                intent if 'intent' in dir() else "browser_automation", params,
            )
        return self._respond(
            f"🌐 I can drive a browser for you. Give me a URL or task:\n"
            f"  • 'go to https://example.com and find their pricing'\n"
            f"  • 'search Google for \"AI agents 2026\" and extract the first 5 results'\n"
            f"  • 'go to this LinkedIn profile and save the email'\n\n"
            f"Start: `./empire start browser`",
            "browser_automation", params,
        )

    async def _handle_video_research(self, params: dict, ctx: AgentContext) -> dict:
        return self._respond(
            f"🎥 Video research needs the video profile running. Start with `./empire start video`\n\n"
            f"Then:\n"
            f"  • 'watch this YouTube video: <url> and tell me the top 3 takeaways'\n"
            f"  • 'transcribe this podcast: <url>'\n"
            f"  • 'what are people saying about AI agents on TikTok?'",
            "video_research", params,
        )

    async def _handle_inbox(self, params: dict, ctx: AgentContext) -> dict:
        return self._respond(
            f"💬 Inbox needs Chatwoot running. Start: `./empire start leads`\n\n"
            f"Then I can show you all conversations across email, WhatsApp, LinkedIn DMs in one place, "
            f"with AI-drafted replies.",
            "inbox_management", params,
        )
