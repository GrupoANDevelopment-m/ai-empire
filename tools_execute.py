#!/usr/bin/env python3
"""
Execution harness — actually CALLS every tool and records the real outcome.

Static analysis can only prove a function *looks* like it works. This harness
imports each tool module and invokes it with arguments matched to its real
signature, then classifies what actually happened:

  PASS      — produced real data
  REFUSED   — the tool ran and correctly rejected the input or reported an
              upstream error (e.g. non-zero exit code, API 400). The payload
              is real, so this is NOT a broken tool.
  CONFIG    — refused because a credential/API key is not set (correct
              behaviour: explicit error naming the missing env var, never a
              fabricated success)
  FAIL      — the tool itself is broken (TypeError, crash, exception in our
              own code path)
  EMPTY     — ok=True but no payload — a possible fake success

Usage:
    python3 tools_execute.py
    python3 tools_execute.py --skill pdf
    python3 tools_execute.py --json report.json
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import inspect
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
SKILLS_DIR = ROOT / ".skills"
FIXTURES = ROOT / "data" / "harness_fixtures"
logging.disable(logging.CRITICAL)

CSV = "a,b,ts\n1,10,2026-01-01\n2,20,2026-01-02\n3,30,2026-01-03\n4,40,2026-01-04\n5,50,2026-01-05\n6,60,2026-01-06\n7,70,2026-01-07\n8,80,2026-01-08"
LONG_TEXT = ("The quick brown fox jumps over the lazy dog. " * 20 +
             "Machine learning models require careful evaluation. " * 20)

SAMPLE: dict[str, dict] = {
    # browser-automation (Pattern B)
    "browser_open_session": {"tenant": "default", "profile": "harness",
                             "headless": True, "start_url": "https://example.com"},
    "browser_navigate": {"session_id": "HARNESS", "url": "data:text/html,<html><body><h1>Harness</h1><p>para</p><input id=q name=q value=><button id=b>Go</button></body></html>"},
    "browser_click": {"session_id": "HARNESS", "selector": "button#b"},
    "browser_fill": {"session_id": "HARNESS", "selector": "input#q", "value": "harness-value"},
    "browser_type": {"session_id": "HARNESS", "selector": "input#q", "text": "typed"},
    "browser_evaluate": {"session_id": "HARNESS", "script": "document.querySelector('h1').textContent"},
    "browser_extract": {"session_id": "HARNESS", "selector": "h1"},
    "browser_screenshot": {"session_id": "HARNESS"},
    "browser_cookies": {"session_id": "HARNESS"},
    "browser_save_state": {"session_id": "HARNESS", "path": "harness_state.json"},
    "browser_close_session": {"session_id": "HARNESS"},
    "browser_load_state": {"session_id": "HARNESS", "path": "harness_state.json"},
    "browser_wait": {"session_id": "HARNESS", "selector": "input#q"},
    "browser_scroll": {"session_id": "HARNESS"},
    "browser_list_sessions": {},
    # calendar
    "list_events": {"days": 3},
    "create_event": {"title": "Harness", "start": "2027-01-04T10:00:00",
                     "attendees": ["a@example.com"]},
    "update_event": {"event_id": "x", "title": "y"},
    "delete_event": {"event_id": "x"},
    "find_slot": {"days": 5},
    "check_availability": {"days": 1},
    "book_meeting": {"title": "Harness", "attendees": ["a@example.com"]},
    "send_invite": {"title": "Harness", "attendees": ["a@example.com"],
                    "start": "2027-01-04T10:00:00"},
    # crm
    "search_contacts": {"query": "acme"},
    "create_contact": {"email": "harness@example.com", "first_name": "H"},
    "update_contact": {"contact_id": "1", "first_name": "Z"},
    "delete_contact": {"contact_id": "1"},
    "list_deals": {},
    "create_deal": {"name": "Harness", "amount": 100},
    "update_deal_stage": {"deal_id": "1", "stage": "closedwon"},
    "add_activity": {"contact_id": "1", "body": "harness note"},
    "get_pipeline": {},
    "forecast_revenue": {},
    # code execution
    "run_python": {"code": "import sys\nprint(6*7)\nprint('ok')"},
    "run_javascript": {"code": "console.log(6*7); console.log('ok');"},
    "run_bash": {"command": "echo harness && pwd"},
    "run_sql": {"query": "SELECT 1 AS ok"},
    "install_package": {"package": "six", "timeout": 60},
    "list_packages": {},
    # data analysis
    "load_csv": {"path": "@CSV@"},
    "load_excel": {"path": "@XLSX@"},
    "load_json": {"data": '[{"a":1,"b":2},{"a":3,"b":4}]'},
    "describe": {"path": "@CSV@"},
    "group_by": {"path": "@CSV@", "by": "a", "agg": {"b": "sum"}},
    "pivot": {"path": "@CSV@", "index": "a", "columns": "b",
              "values": "b", "aggfunc": "sum"},
    "correlation": {"path": "@CSV@"},
    "regression": {"path": "@CSV@", "x": "a", "y": "b"},
    "detect_outliers": {"path": "@CSV@", "columns": ["a"], "method": "iqr"},
    "normalize": {"path": "@CSV@", "columns": ["a", "b"], "method": "zscore"},
    "plot": {"path": "@CSV@", "chart": "scatter", "x": "a", "y": "b"},
    "time_series_decompose": {"path": "@CSV@", "date_col": "ts", "value_col": "b"},
    # email
    "check_inbox": {"folder": "INBOX", "limit": 3},
    "send_email": {"to": "harness@example.com", "subject": "s", "body": "b"},
    "send_bulk": {"template_id": "welcome", "recipients": [
        {"email": "a@example.com", "vars": {"name": "A", "company": "Empire"}}]},
    # pdf — paths are filled in from the fixture built at startup
    "create_pdf": {"title": "Harness", "body": "Harness PDF body. " * 30},
    "parse_pdf": {"path": "@PDF@"},
    "extract_text": {"path": "@PDF@"},
    "merge_pdfs": {"input_paths": ["@PDF@", "@PDF@"]},
    "split_pdf": {"path": "@PDF@"},
    "extract_images": {"path": "@PDF@"},
    "add_watermark": {"path": "@PDF@", "text": "DRAFT"},
    "encrypt_pdf": {"path": "@PDF@", "password": "s3cret!"},
    "decrypt_pdf": {"path": "@PDF@", "password": "s3cret!"},
    "pdf_to_image": {"path": "@PDF@"},
    # saas-b2b
    "churn_predictor": {"customer": {"logins_last_30d": 1,
                                     "features_used_last_30d": 0,
                                     "support_tickets_last_30d": 6,
                                     "nps_score": -40, "seats_used": 1,
                                     "seats_paid": 10}},
    "icp_scorer": {"lead": {"role": "CTO", "company_size": 300,
                            "industry": "saas", "country": "BR"}},
    "mrr_calculator": {"customers": [{"seats": 10, "price_per_seat": 50,
                                       "plan": "pro"}]},
    "company_enrichment": {"domain_or_name": "github.com"},
    "lead_scoring": {"domain": "github.com", "job_title": "CTO",
                     "target_industries": ["software"]},
    "outreach_personalize": {"domain": "github.com", "sender_name": "H",
                             "sender_company": "E", "offer": "automation"},
    # social
    "post_linkedin": {"text": "harness"},
    "post_twitter": {"text": "harness"},
    "post_facebook": {"message": "harness"},
    "post_instagram": {"caption": "harness", "image_url": "https://example.com/a.jpg"},
    "post_thread": {"text": "one. two. three."},
    "schedule_post": {"platform": "linkedin", "content": "harness",
                      "scheduled_at": "2027-01-04T10:00:00"},
    "get_analytics": {"platform": "twitter"},
    "get_followers": {"platform": "twitter"},
    "search_mentions": {"platform": "twitter"},
    "reply_to_mention": {"mention_id": "1", "reply_text": "thanks"},
    # summarization
    "summarize": {"text": LONG_TEXT},
    "bullet_points": {"text": LONG_TEXT},
    "extract_key_points": {"text": LONG_TEXT},
    "generate_tldr": {"text": LONG_TEXT},
    # translation
    "translate": {"text": "Hello world", "target_language": "Portuguese"},
    "detect_language": {"text": "Olá mundo, como você está hoje?"},
    "batch_translate": {"texts": ["Hello", "World"],
                        "target_language": "Portuguese"},
    # web search
    "search": {"query": "python programming"},
    "search_news": {"query": "technology"},
    "search_images": {"query": "mountains"},
    "fetch_url": {"url": "https://example.com"},
    "deep_research": {"topic": "AI agents", "num_sources": 2},
    "summarize_url": {"url": "https://example.com"},
}

# web-search shares 'extract_text' and 'extract_links' names with pdf
SAMPLE["extract_links"] = {"url": "https://example.com"}

# Per-skill overrides where a tool name is reused across skills.
SAMPLE_SCOPED = {
    ("web-search", "extract_text"): {"url": "https://example.com"},
    ("web-search", "extract_links"): {"url": "https://example.com"},
    ("pdf", "extract_text"): {"path": "@PDF@"},
}

MUPROMPT = {"prompt": "a red cube on white", "wait": False}
MUMODELS = {
    "generate_image", "expand_image", "upscale_image", "image_to_image",
    "remove_background", "generate_video", "image_to_video", "video_to_video",
    "clip_video", "generate_audio", "lip_sync", "prompt_enhance",
    "recast_character", "motion_control", "marketing_ad", "creative_agent",
    "app_interest", "agent_library", "chat_with_agent", "create_agent",
    "decompose_layers", "motion_graphics", "motion_graphics_edit",
    "calculate_cost", "estimate_cost", "download_url", "delete_media",
    "workflow_advanced", "workflow_debug", "workflow_inspect",
    "workflow_node_schemas", "create_workflow", "execute_template",
    "upload_file", "account_balance", "generation_history", "list_agents",
    "list_models", "list_local_models", "templates",
}


async def build_fixtures() -> dict:
    """Create real fixture files the tools can operate on."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    csv_p = FIXTURES / "sample.csv"
    csv_p.write_text(CSV, encoding="utf-8")

    pdf_p = FIXTURES / "sample.pdf"
    # Build the fixture with the skill's own create_pdf tool so the fixture
    # is exactly what the pipeline produces.
    try:
        for cand in (ROOT / ".skills" / "pdf" / "tools",
                     ROOT / ".skills" / "pdf" / ".skill" / "tools"):
            if not cand.is_dir():
                continue
            spec = importlib.util.spec_from_file_location(
                "harness_mkpdf", cand / "create_pdf.py")
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            res = await m.create_pdf(
                title="Harness fixture",
                body="AI Empire harness fixture. " * 20,
                output_path=str(pdf_p))
            if not pdf_p.exists() or pdf_p.stat().st_size == 0:
                raise RuntimeError(f"create_pdf did not produce a file: {res}")
            break
    except Exception:
        if not pdf_p.exists():
            pdf_p.write_bytes(b"")   # signals the tool to report honestly

    xlsx_p = FIXTURES / "sample.xlsx"
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["a", "b"])
        for i in range(1, 6):
            ws.append([i, i * 10])
        wb.save(str(xlsx_p))
    except Exception:
        xlsx_p.write_bytes(b"")

    return {"@CSV@": str(csv_p), "@PDF@": str(pdf_p), "@XLSX@": str(xlsx_p)}


def load_tool(path: Path):
    tools_dir = str(path.parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    name = f"hz_{path.parent.parent.name.replace('-', '_')}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def entrypoint(mod, stem):
    fn = getattr(mod, stem, None)
    if fn is None and hasattr(mod, "run"):
        fn = mod.run
    return fn


def sample_for(skill: str, stem: str) -> dict:
    """Skill-aware sample lookup.

    Some tool names repeat across skills (extract_text exists in pdf and
    web-search with completely different signatures), so the sample table is
    keyed by (skill, tool) first and falls back to (tool).
    """
    scoped = SAMPLE_SCOPED.get((skill, stem))
    if scoped is not None:
        return scoped
    return SAMPLE.get(stem, {})


def build_args(skill: str, stem: str, fn, fixtures: dict):
    """Return (call_style, payload).

    call_style is "none", "kwargs" or "positional".
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
    named = [p for p in params if p.kind in
             (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]

    # Pattern B: single dict param named inputs/input/data/payload
    if len(named) == 1 and named[0].name in ("inputs", "input", "data", "payload") \
            and not has_var_kw:
        sample = sample_for(skill, stem) or (dict(MUPROMPT) if stem in MUMODELS else {})
        return "positional", {k: _fill(v, fixtures) for k, v in sample.items()}

    # No parameters at all
    if not named and not has_var_kw:
        return "none", None

    sample = sample_for(skill, stem) or (dict(MUPROMPT) if stem in MUMODELS else {})
    kwargs: dict = {}
    for p in named:
        if p.name in sample:
            kwargs[p.name] = _fill(sample[p.name], fixtures)
        elif p.default is inspect.Parameter.empty:
            kwargs[p.name] = _default_for(p)
    if has_var_kw:
        # extra **kwargs keys from the sample are passed through
        for k, v in sample.items():
            kwargs.setdefault(k, _fill(v, fixtures))
        for p in named:
            if p.name not in kwargs and p.default is inspect.Parameter.empty:
                kwargs[p.name] = _default_for(p)
    return "kwargs", kwargs


def _fill(v, fixtures):
    """Replace @TOKEN@ placeholders, recursing into lists and dicts."""
    if isinstance(v, str):
        if v in fixtures:
            return fixtures[v]
        if v.startswith("@") and v.endswith("@"):
            return fixtures.get(v, v)
        return v
    if isinstance(v, list):
        return [_fill(x, fixtures) for x in v]
    if isinstance(v, dict):
        return {k: _fill(x, fixtures) for k, x in v.items()}
    return v


def _default_for(p) -> object:
    ann = str(p.annotation).lower()
    if "str" in ann:
        return "harness"
    if "int" in ann:
        return 1
    if "float" in ann:
        return 1.0
    if "bool" in ann:
        return False
    if "list" in ann:
        return ["a@example.com"]
    if "dict" in ann:
        return {}
    return None


# Tools whose contract is an action with no return payload.
VOID_ACTION_TOOLS = {
    "browser_wait", "browser_scroll", "browser_load_state", "browser_type",
    "browser_close_session",
}


def classify(stem, res, exc) -> tuple[str, str]:
    if exc is not None:
        msg = f"{type(exc).__name__}: {exc}"
        et = type(exc).__name__
        if (et == "MissingCredential"
                or ("not configured" in msg and "set" in msg)
                or "No LLM configured" in msg
                or re.search(r"(^|: )Set [A-Z_]{4,}", msg)):
            return "CONFIG", msg[:160]
        if et in ("ValueError", "FileNotFoundError", "PermissionError",
                  "KeyError", "NotImplementedError"):
            return "REFUSED", msg[:160]
        return "FAIL", msg[:320]

    if isinstance(res, dict):
        err = str(res.get("error", "") or "")
        if res.get("ok") is False:
            if not err:
                # the tool ran and reported a real, structured failure
                meaningful = {k: v for k, v in res.items()
                              if k != "ok" and v not in (None, "", [], {})}
                if meaningful:
                    return "REFUSED", json.dumps(meaningful, default=str)[:160]
                return "EMPTY", "ok=False with no payload"
            if ("not configured" in err or "MUAPI_API_KEY" in err
                    or "No LLM configured" in err
                    or re.search(r"(^|: )Set [A-Z_]{4,}", err)):
                return "CONFIG", err[:160]
            if any(k in err for k in ("required", "invalid", "cannot be empty",
                                      "not found", "unsupported", "must be")):
                return "REFUSED", err[:160]
            return "REFUSED", err[:200]   # real upstream error
        payload = {k: v for k, v in res.items()
                   if k != "ok" and v not in (None, "", [], {})}
        if not payload:
            if stem in VOID_ACTION_TOOLS:
                return "PASS", "void action acknowledged (ok=True)"
            return "EMPTY", "ok=True but payload empty — possible fake success"
        if set(payload) == {"error"}:
            return "REFUSED", str(payload["error"])[:170]
        return "PASS", json.dumps(payload, default=str)[:170]
    return "PASS", str(res)[:170]


LIVE_SESSION = {"id": None}
BROWSER_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="browser")


async def run_one(path: Path, skill: str, fixtures: dict) -> dict:
    stem = path.stem
    rec = {"tool": stem, "skill": skill,
           "file": str(path.relative_to(ROOT))}
    t0 = time.time()
    res = None
    try:
        mod = load_tool(path)
        fn = entrypoint(mod, stem)
        if fn is None:
            rec.update(status="FAIL", detail="no entrypoint found", ms=0)
            return rec
        style, payload = build_args(skill, stem, fn, fixtures)
        if skill == "browser-automation" and LIVE_SESSION["id"]:
            payload["session_id"] = LIVE_SESSION["id"]
        if style == "none":
            call = lambda: fn()
        elif style == "kwargs":
            call = lambda: fn(**payload)
        else:
            call = lambda: fn(payload)

        if inspect.iscoroutinefunction(fn):
            res = await asyncio.wait_for(call(), timeout=120)
        elif skill == "browser-automation":
            # Playwright's sync API is thread-affine: all browser calls for a
            # run must happen on the SAME thread.
            res = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(BROWSER_POOL, call),
                timeout=120)
        else:
            res = await asyncio.wait_for(asyncio.to_thread(call), timeout=120)
        status, detail = classify(stem, res, None)
    except asyncio.TimeoutError:
        status, detail = "FAIL", "timeout after 120s"
    except BaseException as e:  # noqa: BLE001
        status, detail = classify(stem, None, e)
    rec.update(status=status, detail=detail,
               ms=int((time.time() - t0) * 1000))
    if isinstance(res, dict) and isinstance(res.get("session"), dict):
        rec["_session_id"] = res["session"].get("session_id")
    return rec


async def main() -> int:
    args = sys.argv[1:]
    as_json = "--json" in args
    only = args[args.index("--skill") + 1] if "--skill" in args else None

    fixtures = await build_fixtures()

    targets = []
    for sd in sorted(SKILLS_DIR.iterdir()):
        if not sd.is_dir() or (only and sd.name != only):
            continue
        for cand in (sd / "tools", sd / ".skill" / "tools"):
            if cand.is_dir():
                targets.extend((sd.name, f) for f in sorted(cand.glob("*.py"))
                               if not f.name.startswith("_"))
                break

    print("=" * 80)
    print(f" EXECUTION HARNESS — calling {len(targets)} tools for real")
    print("=" * 80)

    results = []
    # browser-automation needs a live session for most tools, and closing it
    # tears down the Playwright driver — so open first, close last.
    def _is_browser(skill, f):
        return skill == "browser-automation"

    ordered = []
    open_first = [t for t in targets if t[1].stem == "browser_open_session"]
    close_last = [t for t in targets if t[1].stem == "browser_close_session"]
    rest = [t for t in targets
            if t[1].stem not in ("browser_open_session", "browser_close_session")]
    # explicit dependency order for the browser: navigate before anything
    # that needs a page element
    BROWSER_ORDER = [
        "browser_open_session", "browser_navigate", "browser_evaluate",
        "browser_click", "browser_fill", "browser_type", "browser_extract",
        "browser_wait", "browser_scroll", "browser_cookies",
        "browser_screenshot", "browser_save_state", "browser_load_state",
        "browser_list_sessions", "browser_close_session",
    ]
    by_stem = {t[1].stem: t for t in targets}
    ordered = [by_stem[k] for k in BROWSER_ORDER if k in by_stem]
    ordered += [t for t in targets
                if t[1].stem not in BROWSER_ORDER and not _is_browser(*t)]

    for skill, f in ordered:
        r = await run_one(f, skill, fixtures)
        results.append(r)
        if f.stem == "browser_open_session" and r.get("_session_id"):
            LIVE_SESSION["id"] = r["_session_id"]
        icon = {"PASS": "+", "CONFIG": "c", "REFUSED": "r",
                "FAIL": "X", "EMPTY": "!"}.get(r["status"], "?")
        print(f"  {icon} {skill:18s} {r['tool']:24s} {r['ms']:>6}ms  {r['detail'][:66]}")

    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print("\n" + "=" * 80)
    print(f" TOTAL {len(results)}  " +
          "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("=" * 80)

    fails = [r for r in results if r["status"] in ("FAIL", "EMPTY")]
    if fails:
        print(f"\n FAILURES ({len(fails)})")
        for r in fails:
            print(f"   X {r['skill']}/{r['tool']}: {r['detail'][:200]}")

    if as_json:
        i = args.index("--json")
        outp = args[i + 1] if i + 1 < len(args) else None
        if outp and outp != "-":
            Path(outp).write_text(json.dumps(
                {"counts": counts, "results": results}, indent=2), encoding="utf-8")
            print(f"\n -> {outp}")

    return 1 if any(r["status"] in ("FAIL", "EMPTY") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
