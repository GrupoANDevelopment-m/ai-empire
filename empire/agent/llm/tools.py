"""
Tools the LLM can call. Each tool is a Python function with a docstring
that becomes its description. The LLM reads the docstring to decide
when to call it.
"""
from __future__ import annotations
import json
import asyncio
import logging
import os
import subprocess
import httpx
from pathlib import Path
from typing import Any

log = logging.getLogger("empire.tools")


# ============================================================================
# Tool 1: find_leads — discover leads
# ============================================================================
async def find_leads(goal: str, limit: int = 20, industry: str | None = None, geo: str | None = None) -> str:
    """
    Find B2B leads matching a goal. Use when the user asks to find,
    get, source, or search for leads, prospects, contacts, or people.

    Args:
        goal: Description of who you want, e.g. "SaaS CTOs in Brazil"
        limit: How many leads to return (default 20, max 100)
        industry: Optional industry filter (SaaS, Fintech, etc.)
        geo: Optional geography filter ("Brazil", "São Paulo", "France")

    Returns: A summary of leads found, with name, role, company, email.

    Strategy: tries three backends in order.
      1. CrewAI/LangGraph leads crew on :8123 (best — uses Apify/Clearbit/OpenOutreach)
      2. Local Playwright + duckduckgo-search (no infra needed, slower)
      3. Error if neither is reachable
    """
    # 1. Try the proper leads crew
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "http://localhost:8123/crews/leads",
                json={"goal": goal, "limit": limit, "industry": industry, "geo": geo},
            )
            if r.status_code == 200:
                return _format_leads(r.json().get("leads", []), "CrewAI", goal)
    except Exception as e:
        leads_crew_error = str(e)

    # 2. Fall back to local Playwright + DDG (works without Docker)
    try:
        import subprocess
        script = Path(__file__).parent.parent.parent.parent / "scripts" / "real_leads.py"
        if script.exists():
            result = subprocess.run(
                ["python3", str(script), goal, str(limit)],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode == 0:
                out_file = Path("/tmp/empire_leads_angola.json")
                if out_file.exists():
                    data = json.loads(out_file.read_text())
                    return _format_leads(data.get("leads", []), "Playwright+DDG (local)", goal)
    except Exception as e:
        local_error = str(e)

    return (
        f"Could not find leads. Tried:\n"
        f"  1. CrewAI crew at :8123 — not running (docker compose --profile agents --profile leads up -d)\n"
        f"  2. Local Playwright fallback — failed: {local_error if 'local_error' in dir() else 'scripts/real_leads.py not installed (pip install playwright duckduckgo-search beautifulsoup4 lxml && playwright install chromium)'}\n"
        f"Original error: {leads_crew_error if 'leads_crew_error' in dir() else 'unknown'}"
    )


def _format_leads(leads: list, engine: str, goal: str) -> str:
    if not leads:
        return f"No leads found for '{goal}'."
    lines = [f"Found {len(leads)} leads (via {engine}):"]
    for i, lead in enumerate(leads[:20], 1):
        name = lead.get("name", "?")
        company = lead.get("company") or lead.get("organization") or "?"
        role = lead.get("role", "?")
        score = lead.get("score", "?")
        email = lead.get("email", "no email")
        src = lead.get("source", "")
        src_str = f" [src: {src}]" if src else ""
        lines.append(f"  {i}. {name} — {role} at {company} (score {score}, {email}){src_str}")
    if len(leads) > 20:
        lines.append(f"  ... and {len(leads) - 20} more")
    Path("/tmp/empire_last_leads.json").write_text(json.dumps(leads))
    lines.append("\n(Saved to /tmp/empire_last_leads.json for follow-up actions)")
    return "\n".join(lines)


# ============================================================================
# Tool 2: send_outreach — draft a cold email / message
# ============================================================================
async def send_outreach(lead_index: int = 1, channel: str = "email") -> str:
    """
    Send outreach to a previously-found lead. Use after find_leads when
    the user says "send", "write", "draft", "contact", "reach out".

    Args:
        lead_index: Which lead to contact (1-based, from most recent find_leads result)
        channel: "email", "whatsapp", or "linkedin"

    Returns: The drafted message (not actually sent until HITL approval).
    """
    leads_file = Path("/tmp/empire_last_leads.json")
    if not leads_file.exists():
        return "No leads found yet. Run find_leads first."

    leads = json.loads(leads_file.read_text())
    if lead_index < 1 or lead_index > len(leads):
        return f"Invalid lead_index. Found {len(leads)} leads; pick 1-{len(leads)}."

    lead = leads[lead_index - 1]
    name = lead.get("name", "there")
    company = lead.get("company", "your company")
    role = lead.get("role", "")
    industry = lead.get("metadata", {}).get("industry", "your industry")

    if channel == "email":
        return f"""📧 Cold email draft for {name} ({role} at {company}):

Subject: Quick question about {company}'s growth

Hi {name},

I noticed {company} is scaling — congrats on the momentum.
I work with similar {industry} companies and have a few ideas that could
save your team 10+ hours/week on operations and outreach.

Open to a 15-min call this week?

Best,
Mavis

---
⚠️  This is a DRAFT. Confirm with the user before sending.
To actually send, configure SMTP in .env and use the outreach-email skill."""

    if channel == "whatsapp":
        return f"""📱 WhatsApp draft for {name}:

Hi {name}, tudo bem? 👋
Vi que a {company} está crescendo. Tenho uma ideia rápida que pode
economizar 10h/semana do seu time. Posso compartilhar em 2min?
— Mavis

---
⚠️  DRAFT only. Configure Twilio or WhatsApp Cloud API to send."""

    if channel == "linkedin":
        return f"""💼 LinkedIn connection request for {name}:

Hi {name}, I see you're leading {role} at {company}. I'm working with
similar companies on operations automation. Would love to connect and
share some patterns that worked.

---
⚠️  DRAFT only. Needs OpenOutreach running and LinkedIn account configured."""

    return f"Unknown channel: {channel}"


# ============================================================================
# Tool 3: run_tests — execute pytest via natural language
# ============================================================================
async def run_tests(target: str = "all") -> str:
    """
    Run the AI Empire test suite. Use when the user says "test", "run tests",
    "check the tests", "is X working?".

    Args:
        target: What to test. One of:
            - "all" (full unit + e2e suite)
            - "circuit-breaker" / "breaker"
            - "retry" / "backoff"
            - "fallback" / "chain"
            - "self-healing" / "healing"
            - "learning" / "feedback" / "ab-test"
            - "failover" / "server-pool"
            - "e2e" / "end-to-end"
            - "integration"

    Returns: Human-readable test result with pass/fail counts.
    """
    PROJECT_ROOT = "/workspace/ai-empire/orchestrator"
    target_map = {
        "all": "tests/",
        "circuit-breaker": "tests/test_circuit_breaker.py",
        "breaker": "tests/test_circuit_breaker.py",
        "retry": "tests/test_retry.py",
        "backoff": "tests/test_retry.py",
        "fallback": "tests/test_fallback.py",
        "chain": "tests/test_fallback.py",
        "self-healing": "tests/test_self_healing.py",
        "healing": "tests/test_self_healing.py",
        "learning": "tests/test_learning.py",
        "feedback": "tests/test_learning.py",
        "ab-test": "tests/test_learning.py",
        "abtest": "tests/test_learning.py",
        "failover": "tests/test_failover.py",
        "server-pool": "tests/test_failover.py",
        "e2e": "tests/test_e2e_self_healing.py",
        "end-to-end": "tests/test_e2e_self_healing.py",
        "integration": "tests/test_gateway_integration.py",
    }
    test_target = target_map.get(target.lower(), "tests/")

    if test_target == "tests/":
        cmd = ["python3", "-m", "pytest", "tests/", "-v", "--tb=line",
               "--ignore=tests/chaos", "--ignore=tests/test_gateway_integration.py"]
    else:
        cmd = ["python3", "-m", "pytest", test_target, "-v", "--tb=line"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=PROJECT_ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        out = stdout.decode("utf-8", errors="replace")
        rc = proc.returncode
    except asyncio.TimeoutError:
        return "⏱️  Tests timed out after 5 minutes."
    except Exception as e:
        return f"❌ Could not run tests: {e}\nMake sure you're in /workspace/ai-empire."

    # Parse the summary
    import re
    passed = failed = skipped = 0
    m = re.search(r"(\d+)\s+passed", out)
    if m: passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", out)
    if m: failed = int(m.group(1))
    m = re.search(r"(\d+)\s+skipped", out)
    if m: skipped = int(m.group(1))

    if rc == 0:
        msg = f"✅ All {passed} tests passed"
        if skipped:
            msg += f" ({skipped} skipped because services not running)"
        # Last 2 lines (the pytest summary)
        last = "\n".join(out.strip().split("\n")[-2:])
        return f"{msg}.\n\n{last}"
    else:
        msg = f"❌ {failed} failed, {passed} passed"
        if skipped:
            msg += f", {skipped} skipped"
        # Find the failure details
        failures = []
        for m in re.finditer(r"FAILED\s+(.+?)(?=\n)", out):
            failures.append(f"  • {m.group(1)}")
            if len(failures) >= 5:
                break
        last = "\n".join(out.strip().split("\n")[-3:])
        result = f"{msg}\n\n"
        if failures:
            result += "Failures:\n" + "\n".join(failures) + "\n\n"
        result += f"```\n{last}\n```"
        return result


# ============================================================================
# Tool 4: health_check — check what's running
# ============================================================================
async def health_check() -> str:
    """
    Check the health of all AI Empire services. Use when the user says
    "is X running", "is everything up", "health check", "what's running",
    "show status".

    Returns: A status report of each major service.
    """
    services = [
        ("LangGraph (orchestrator)", "http://localhost:8123/health"),
        ("Ollama (local LLM)", "http://localhost:11434/api/tags"),
        ("Open WebUI", "http://localhost:3000"),
        ("n8n (workflows)", "http://localhost:5678"),
        ("ComfyUI (image gen)", "http://localhost:8188"),
        ("Penpot (design)", "http://localhost:9001"),
        ("LiteLLM (AI gateway)", "http://localhost:4000/health/liveliness"),
        ("Browser-Use", "http://localhost:8001/health"),
    ]
    results = []
    async with httpx.AsyncClient(timeout=3) as client:
        for name, url in services:
            try:
                r = await client.get(url)
                status = "✅ up" if r.status_code in (200, 204) else f"⚠️  {r.status_code}"
            except Exception:
                status = "❌ down"
            results.append(f"  {status}  {name}")
    return "Here's what's running:\n\n" + "\n".join(results) + \
           "\n\nTo start a profile: docker compose --profile <name> up -d"


# ============================================================================
# Tool 5: generate_image — request an image
# ============================================================================
async def generate_image(prompt: str, aspect_ratio: str = "1:1") -> str:
    """
    Generate an image. Use when the user wants to "create", "generate",
    "make", "draw" an image, picture, illustration, banner, thumbnail.

    Args:
        prompt: Description of the image (e.g. "minimalist SaaS dashboard illustration")
        aspect_ratio: "1:1" (square), "16:9" (landscape), "9:16" (vertical/Story), "4:5" (portrait)

    Returns: Path to the generated image, with an honest note about which
    tier produced it (T0 = real GPU model, T1 = quantized CPU model,
    T2 = procedural CPU fallback).

    Strategy: tries 3 tiers.
      1. ComfyUI on :8188 (real FLUX/SD on GPU) — best quality, needs Docker + GPU
      2. Stable Diffusion 1.5 ONNX int8 on CPU — slow but real, needs model download
      3. PIL procedural gradient — always works, not a real AI image
    """
    # Use the unified media engine (handles all tiers with honest reporting)
    script = Path(__file__).parent.parent.parent.parent / "scripts" / "media_engine.py"
    if script.exists():
        try:
            import subprocess
            result = subprocess.run(
                ["python3", str(script), "image", prompt, "--aspect", aspect_ratio],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                import json as _json
                r = _json.loads(result.stdout)
                tier = r.get("tier", "?")
                model = r.get("model", "?")
                took = r.get("took_sec", 0)
                path = r.get("path", "")
                note = r.get("note", "")
                return (
                    f"✅ Image generated [{tier}] in {took}s\n"
                    f"   Model: {model}\n"
                    f"   Path: {path}\n"
                    f"   Prompt: {prompt}\n"
                    f"   Note: {note}"
                )
        except Exception:
            pass

    # Last-resort direct fallback
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "http://localhost:8188/prompt",
                json={"prompt": prompt, "aspect_ratio": aspect_ratio},
            )
            if r.status_code == 200:
                data = r.json()
                return f"✅ Image (ComfyUI): {data.get('image_url', 'check ComfyUI output folder')}\nPrompt: {prompt}"
    except Exception as e:
        return f"❌ No image engine available. Error: {e}\nStart ComfyUI: docker compose --profile design up -d (needs GPU)"


# ============================================================================
# Tool 6: navigate_browser — drive a browser with LLM
# ============================================================================
async def navigate_browser(goal: str) -> str:
    """
    Drive a real browser (browser-use) to do a task. Use when the user
    says "go to", "open", "navigate", "fill", "click", "extract from",
    or wants to interact with any website.

    Args:
        goal: What you want the browser to do, e.g. "Go to https://example.com and find their pricing email"

    Returns: The browser task result.
    """
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                "http://localhost:8001/task",
                json={"goal": goal, "max_steps": 20},
            )
            if r.status_code == 200:
                data = r.json()
                return f"🌐 Browser task completed:\n\n{data.get('result', 'no result')}"
    except Exception as e:
        return f"❌ Browser service not reachable at localhost:8001 ({e}).\nStart it: docker compose --profile browser up -d"
    return "❌ Browser service returned an error."


# ============================================================================
# Tool 7: publish_social — post to social media
# ============================================================================
async def publish_social(text: str, channels: list[str] | None = None) -> str:
    """
    Publish a post to one or more social media channels. Use when the user
    says "post", "publish", "share", "tweet", "post to twitter/linkedin/...".

    Args:
        text: The content to publish
        channels: List of channels, e.g. ["twitter", "linkedin", "telegram"]. Default: ["twitter", "linkedin"]

    Returns: A summary of what was published where.
    """
    channels = channels or ["twitter", "linkedin"]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "http://localhost:5678/webhook/empire-publish",
                json={"content": {"title": "", "body": text, "tags": []}, "channels": channels},
            )
            if r.status_code == 200:
                return f"📢 Published to {', '.join(channels)}:\n\n{text[:200]}..."
    except Exception as e:
        return f"❌ n8n not reachable at localhost:5678 ({e}).\nStart it: docker compose --profile core up -d"
    return "❌ n8n returned an error."


# ============================================================================
# Tool 8: generate_video — create a short video from text
# ============================================================================
async def generate_video(prompt: str, duration_seconds: int = 5,
                         aspect_ratio: str = "16:9") -> str:
    """
    Generate a short video from a text prompt. Use when the user says
    "make a video", "animate", "create a clip", "video of...".

    Args:
        prompt: Description of the video (e.g. "a cat walking in the rain")
        duration_seconds: Target length in seconds (1-10)
        aspect_ratio: "16:9" (landscape), "9:16" (vertical/Story), "1:1" (square)

    Returns: Path to the generated video and an honest note about which
    tier produced it.
      T0 = Open-Sora 2.0 on GPU (best quality)
      T1 = CogVideoX-2B INT8 on CPU (real AI, slow)
      T2 = ffmpeg gradient procedural (always works, not real AI)
    """
    script = Path(__file__).parent.parent.parent.parent / "scripts" / "media_engine.py"
    if script.exists():
        try:
            import subprocess, traceback
            result = subprocess.run(
                ["python3", str(script), "video", prompt,
                 "--duration", str(duration_seconds),
                 "--aspect", aspect_ratio],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                import json as _json
                r = _json.loads(result.stdout)
                tier = r.get("tier", "?")
                model = r.get("model", "?")
                took = r.get("took_sec", 0)
                path = r.get("path", "")
                note = r.get("note", "")
                return (
                    f"✅ Video generated [{tier}] in {took}s\n"
                    f"   Model: {model}\n"
                    f"   Path: {path}\n"
                    f"   Prompt: {prompt}\n"
                    f"   Note: {note}"
                )
            else:
                return (
                    f"❌ media_engine.py failed (rc={result.returncode})\n"
                    f"   stderr: {result.stderr[:300]}\n"
                    f"   stdout: {result.stdout[:300]}"
                )
        except Exception as e:
            return (
                f"❌ Subprocess failed: {type(e).__name__}: {e}\n"
                f"   traceback: {traceback.format_exc()[:500]}"
            )
    return (
        f"❌ media_engine.py not found at {script}. "
        f"Options:\n"
        f"  • T0 (best): docker compose --profile video up -d (needs GPU 24GB+)\n"
        f"  • T1 (real AI on CPU): pip install diffusers torchao, "
        f"download CogVideoX-2B to /opt/empire/models/cogvideox-2b\n"
        f"  • T2 (always works): install ffmpeg"
    )


# ============================================================================
# Tool 9: watch_video — research a video
# ============================================================================
async def watch_video(url: str) -> str:
    """
    Watch and summarize a video (YouTube, TikTok, podcast, etc).
    Use when the user says "watch", "summarize", "what does this video say",
    "transcribe".

    Args:
        url: The video URL (YouTube, TikTok, etc.)

    Returns: A summary of the video with key takeaways.
    """
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                "http://localhost:8123/crews/research",
                json={"urls": [url], "topic": ""},
            )
            if r.status_code == 200:
                data = r.json()
                return f"🎥 Video summary:\n\n{data.get('report', 'No report')}"
    except Exception as e:
        return f"❌ Orchestrator not reachable ({e}).\nStart it: docker compose --profile agents up -d"
    return "❌ Could not process video."


# ============================================================================
# Tool registry — turns Python functions into LLM tool definitions
# ============================================================================

def tool_definitions() -> list[dict]:
    """Return OpenAI-format tool definitions for all tools."""
    tools = [
        find_leads, send_outreach, run_tests, health_check,
        generate_image, navigate_browser, publish_social, watch_video,
        generate_video,
    ]
    return [
        {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": (fn.__doc__ or "").strip().split("\n\n")[0],
                "parameters": _params_from_signature(fn),
            },
        }
        for fn in tools
    ]


def _params_from_signature(fn) -> dict:
    """Generate a JSON schema from a Python function's signature + docstring."""
    import inspect
    sig = inspect.signature(fn)
    properties = {}
    required = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        ann = param.annotation
        t = "string"
        if ann in (int,):
            t = "integer"
        elif ann in (bool,):
            t = "boolean"
        elif ann == list or (hasattr(ann, "__origin__") and ann.__origin__ == list):
            t = "array"
        # Get description from docstring (the "Args:" block)
        properties[name] = {"type": t, "description": _docstring_param(fn, name)}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _docstring_param(fn, name: str) -> str:
    """Pull a parameter description from the docstring's Args: block."""
    doc = fn.__doc__ or ""
    in_args = False
    for line in doc.split("\n"):
        if "Args:" in line:
            in_args = True
            continue
        if in_args:
            if line.strip() == "":
                in_args = False
                continue
            if ":" in line and not line.startswith(" "):
                break
            stripped = line.strip()
            if stripped.startswith(f"{name}:"):
                return stripped[len(name) + 1:].strip()
            if stripped.startswith(f"{name} "):
                return stripped[len(name) + 1:].strip()
    return name


# Dispatch
TOOL_FUNCTIONS = {
    "find_leads": find_leads,
    "send_outreach": send_outreach,
    "run_tests": run_tests,
    "health_check": health_check,
    "generate_image": generate_image,
    "navigate_browser": navigate_browser,
    "publish_social": publish_social,
    "watch_video": watch_video,
    "generate_video": generate_video,
}


async def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments."""
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return await fn(**arguments)
    except TypeError as e:
        return f"Wrong arguments for {name}: {e}"
    except Exception as e:
        return f"Error in {name}: {type(e).__name__}: {e}"
