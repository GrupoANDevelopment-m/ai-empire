# AI Empire v4.0 — Release Notes

**Data:** 2026-03-09
**Tag:** v4.0
**Commit:** `932c165`

---

## Headline

**muapi-studio skill v4.0: 40 production tools** that wire AI Empire directly to the **3 Open Generative AI projects** (Vibe-Workflow, Open-Poe-AI, Open-AI-Design-Agent) via their real backend code, **without rewriting any external project**.

535+ models reachable. Zero stubs. Zero mocks. Zero placeholders.

---

## What changed

### NEW TOOLS (4 added, 40 total)

| Tool | Source project | Real endpoints |
|------|---------------|----------------|
| `workflow_advanced` | SamurAIGPT/Vibe-Workflow | 11 endpoints from `vw/server/app/routers/workflow_router.py` + `utils/workflow_helper.py`: publish, template, signed-url, thumbnail, last-run, architect + poll, api-outputs, update-category, dynamic-cost, file-upload-url |
| `workflow_node_schemas` | SamurAIGPT/Vibe-Workflow | Bundled 121-model catalog from `vw/packages/workflow-builder/src/components/utility.jsx` (42 image + 61 video + 5 text + 7 audio + concat + combiner + 4 api node) — `data/model_catalog.json` |
| `agent_library` | Anil-matcha/Open-Poe-AI | 8 endpoints from `poe/server/app/routers/agent_proxy.py`: suggest_agents, update_agent, like_agent, get_agent_profile, get_agent_skills, preview_realign, get_prediction_result, flux_schnell_image |
| `creative_agent` | Anil-matcha/Open-AI-Design-Agent | 14 endpoints from `da/server/app/routers/creative_agent_router.py` + `utils/muapi_helper.py`: session CRUD, chat, assets (get/register), jobs (list/status/events/approve/reject/cancel), run_skill, agent_skills, account_balance |

### Why these 4 tools (not "yet another wrapper")

Each new tool maps **1-to-1 to a real router file** in the upstream code. No endpoint invented, no path guessed — every URL is the exact one used by the original Vibe-Workflow / Open-Poe-AI / Design-Agent backend that ships to production.

### Architecture

```
AI Empire agent
   ↓ tool call
muapi-studio/<tool>
   ↓ runs in sandbox (heavy profile, isolated)
   ↓ makes HTTP call with x-api-key header
api.muapi.ai/<real-endpoint>
   ↓ same backend as
Open Generative AI / Vibe-Workflow / Open-Poe-AI / Design-Agent
```

No new abstractions. No new protocols. The same MuAPI REST endpoints that the 3 reference projects call, AI Empire calls too. **They coexist.**

---

## Integration statistics

### Catalog extracted (data/model_catalog.json)
```
imageModels:  42
videoModels:  61
textModels:    5
audioModels:   7
concatModels:  1
videoCombinerModels: 1
apiNodeModels: 4
TOTAL:       121
```

### Tool inventory (40)

| Category | Count | Tools |
|----------|-------|-------|
| Generation | 9 | `generate_image`, `generate_video`, `generate_audio`, `image_to_image`, `image_to_video`, `video_to_video`, `lip_sync`, `upload_file`, `list_models` |
| Video editing | 4 | `clip_video`, `motion_graphics`, `motion_graphics_edit`, `recast_character` |
| Motion transfer | 1 | `motion_control` (motion_transfer + objects_swap) |
| Image editing | 4 | `upscale_image`, `remove_background`, `expand_image`, `decompose_layers` |
| Marketing | 1 | `marketing_ad` |
| Templates + account | 4 | `templates`, `execute_template`, `account_balance`, `generation_history` |
| Cost + utils | 5 | `estimate_cost`, `calculate_cost`, `download_url`, `prompt_enhance`, `delete_media` |
| Agents (chat + agent skill) | 5 | `chat_with_agent`, `create_agent`, `list_agents`, `agent_library`, `creative_agent` |
| Workflows | 4 | `create_workflow`, `workflow_inspect`, `workflow_debug`, `workflow_advanced` |
| Bundled catalog | 1 | `workflow_node_schemas` (121 models) |
| Local models | 1 | `list_local_models` (12 sd.cpp + Wan2GP) |
| App interest | 1 | `app_interest` |
| **TOTAL** | **40** | |

---

## Validation

```
AST validation:        40 / 40 ✓ (zero violations)
Sandbox execution:     40 / 40 ✓
Skill self-test:        3 / 3 ✓ (all ok)
Discovery endpoint:    40 / 40 exposed via /api/capabilities
Network policy:        allow [api.muapi.ai, *.muapi.ai, cdn.muapi.ai]
                       deny  [localhost, 127.0.0.1, metadata.*]
```

Every tool:
- Passes AST validator (no subprocess/ctypes/socket/exec/eval/etc.)
- Runs successfully in subprocess sandbox with `heavy` profile (5 CPU sec, 2 GB RAM, 60 s)
- Returns `{"ok": ...}` on valid inputs
- Returns `{"ok": False, "error": "..."}` on invalid/missing inputs (no crashes)

---

## How it was extracted (no rewrites)

1. **Vibe-Workflow** — `vw/server/app/routers/workflow_router.py` (224 lines) read; each `@router.post/get(...)` decorator + URL + handler signature → action in `workflow_advanced.run()`. The `_muapi_call` helper mirrors `proxy_request_helper` from `utils/workflow_helper.py` (HTTP forwarding to `API_SUFFIX/api/v1/...`).
2. **Open-Poe-AI** — `poe/server/app/routers/agent_proxy.py` (91 lines) read; each endpoint → action in `agent_library.run()`. The same proxy pattern is used.
3. **Design-Agent** — `da/server/app/routers/creative_agent_router.py` (188 lines) read; the `/sessions` and `/jobs` CRUD endpoints → actions in `creative_agent.run()`. File upload flow mirrors `proxy_s3_upload`.
4. **Catalog** — `vw/packages/workflow-builder/src/components/utility.jsx` parsed with regex + brace-matching; the 121 model definitions (id + name) extracted to `data/model_catalog.json`.

All extraction is documented in commit messages. No file is modified outside `muapi-studio/`.

---

## No stubs, no mocks, no placeholders

What this skill does NOT do:
- ❌ Does not return hardcoded "demo" responses
- ❌ Does not have any `if DEMO_MODE:` branches
- ❌ Does not fake MuAPI responses
- ❌ Does not use proxies that talk to a local fake server
- ❌ Does not store canned results

What it DOES:
- ✅ Makes real HTTP calls to `api.muapi.ai` with the live `x-api-key` header
- ✅ Returns the actual API response (parsed JSON or raw)
- ✅ Surfaces real errors (`API 401`, `API 404`, `API 422`, etc.)
- ✅ Polls real prediction jobs until status = completed/failed/timeout
- ✅ Bundles the real production model catalog (121 models)

---

## API surface (sample)

```bash
# List all 535+ models reachable
curl -H "x-api-key: $MUAPI_API_KEY" https://api.muapi.ai/openapi.json | jq '.paths | keys | length'

# Via AI Empire (from the agent or /api/capabilities)
empire tools list | grep muapi-studio | wc -l
# 40

# Direct tool invocation via skill registry
empire tool run muapi-studio.workflow_node_schemas category=image limit=5
# {"ok":true,"category":"image","models":[...],"count":5}

# Real workflow publish via Vibe-Workflow backend
empire tool run muapi-studio.workflow_advanced action=publish_workflow workflow_id=abc123
# → POST api.muapi.ai/workflow/workflow/abc123/publish (real call)
```

---

## Files added/modified in v4.0

```
.skills/muapi-studio/
├── skill.yaml                                  (updated: 4 new tools)
├── data/model_catalog.json                     (NEW: 121 models, 10 KB)
└── tools/
    ├── workflow_advanced.py                     (NEW: 11 actions)
    ├── workflow_node_schemas.py                 (NEW: bundled catalog)
    ├── agent_library.py                        (NEW: 8 actions)
    └── creative_agent.py                        (NEW: 14 actions)

Total: 4 new files, 1 updated YAML, 1 bundled data file
```

**LOC**: ~30 KB of pure integration code (no rewrites of external projects).

---

## Backward compatibility

- All 36 v3.0 tools still work identically (AST + sandbox still pass).
- Skill version bumped 3.0.0 → 4.0.0.
- Self-test cases still pass.

---

## Next steps

- v4.1: WebSocket streaming for long-running jobs (architect, video gen)
- v4.1: SSE listener for `get_job_events`
- v4.1: Preset templates from the 65 Vibe-Workflow presets (currently bundled, not exposed)
- v4.2: Multi-key support (per-tenant MUAPI keys)

---

**Tags:** `release/v4.0`, `muapi-studio/v4.0`, `enhancement`

EOF