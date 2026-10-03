"""Model catalog — 121 production models from Vibe-Workflow's utility.jsx.

Real model catalog. Backed by .skills/muapi-studio/data/model_catalog.json
(extracted from SamurAIGPT/Vibe-Workflow's packages/workflow-builder/src/components/utility.jsx).
"""
import json
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "model_catalog.json"


def _load_catalog():
    if not CATALOG_PATH.exists():
        return None
    raw = CATALOG_PATH.read_text()
    return json.loads(raw)


def run(inputs):
    category = (inputs.get("category") or "all").lower()
    search = (inputs.get("search") or "").lower().strip()
    target_id = inputs.get("id")
    limit = int(inputs.get("limit") or 100)

    catalog = _load_catalog()
    if not catalog:
        return {"ok": False, "error": "model_catalog.json not found"}

    category_map = {
        "image": "imageModels", "images": "imageModels", "t2i": "imageModels",
        "video": "videoModels", "videos": "videoModels", "t2v": "videoModels",
        "text": "textModels", "llm": "textModels",
        "audio": "audioModels", "speech": "audioModels", "music": "audioModels",
        "concat": "concatModels",
        "video_combiner": "videoCombinerModels", "combiner": "videoCombinerModels",
        "api": "apiNodeModels", "api_node": "apiNodeModels",
    }

    if target_id:
        for cat_key, items in catalog.items():
            for m in items:
                if m.get("id") == target_id:
                    return {"ok": True, "model": m, "category": cat_key}
        return {"ok": False, "error": f"model id '{target_id}' not found in catalog"}

    if category == "all":
        items = []
        for cat_key, models in catalog.items():
            for m in models:
                m2 = dict(m); m2["_category"] = cat_key
                items.append(m2)
    else:
        key = category_map.get(category)
        if not key:
            return {"ok": False,
                    "error": f"unknown category: {category}. Use image, video, text, audio, "
                              f"concat, video_combiner, api, or all."}
        items = [dict(m) for m in catalog.get(key, [])]
        for m in items: m["_category"] = key

    if search:
        items = [m for m in items
                if search in (m.get("id") or "").lower()
                or search in (m.get("name") or "").lower()]

    items = items[:limit]
    return {
        "ok": True,
        "category": category,
        "search": search or None,
        "models": items,
        "count": len(items),
        "source": "vibe-workflow utility.jsx (extracted from SamurAIGPT/Vibe-Workflow)",
    }
