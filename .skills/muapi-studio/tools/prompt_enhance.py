"""Prompt utilities — enhance, augment, and validate prompts.

Mirrors the prompt enhancement features from Open Generative AI:
- ENHANCE_TAGS, QUICK_PROMPTS, CAMERA_MAP, LENS_MAP, FOCAL_PERSPECTIVE
  (from src/lib/promptUtils.js)
- formatErrorMessage (from utils/formatError.js)

Useful for the LLM to:
- Enrich vague prompts with camera/lens/style details
- Validate input before submitting to expensive models
- Format error messages nicely (parse JSON in error strings)
"""
import json
import re


# Quick prompts (curated by Open Generative AI community)
QUICK_PROMPTS = [
    "A cinematic portrait of a young woman in golden hour light, soft bokeh, shot on 85mm f/1.4",
    "A futuristic cityscape at night with neon lights, rain-soaked streets, cyberpunk aesthetic",
    "A photorealistic product photo of a luxury watch on black marble, dramatic rim lighting",
    "An aerial view of a misty mountain valley at sunrise, volumetric fog, ultra-wide 16mm",
    "A cozy reading nook with warm lamp light, falling snow visible through the window",
    "A macro shot of a dewdrop on a leaf, extreme detail, soft natural light, 100mm macro",
    "An astronaut floating in space with Earth in the background, photorealistic, NASA style",
    "A vintage 1960s diner interior, warm tungsten lighting, retro film grain, 35mm Kodak",
]

# Camera body styles
CAMERA_MAP = {
    "cinematic": "ARRI Alexa, anamorphic lens, shallow depth of field, cinematic color grading",
    "portrait": "Canon EOS R5, 85mm f/1.4, soft natural light, creamy bokeh",
    "landscape": "Nikon Z9, 16-35mm f/2.8, golden hour, polarizing filter, ultra-sharp",
    "street": "Leica M11, 35mm f/1.4, available light, documentary style, film grain",
    "product": "Phase One IQ4, 100mm macro, controlled studio lighting, color-accurate",
    "fashion": "Hasselblad X2D, 80mm f/1.9, high-key lighting, editorial composition",
    "macro": "Canon EOS R5, 100mm f/2.8 macro, ring light, focus-stacked",
    "astro": "Sony A7S III, 14mm f/1.8, long exposure, star tracker, low noise",
}

# Lens / focal length effects
LENS_MAP = {
    "14mm": "extreme wide-angle, dramatic perspective distortion",
    "24mm": "wide-angle, environmental context, slight distortion",
    "35mm": "natural perspective, documentary feel, all-purpose",
    "50mm": "human-eye perspective, versatile, natural compression",
    "85mm": "classic portrait, beautiful bokeh, flattering compression",
    "135mm": "telephoto portrait, strong subject isolation, creamy background",
    "200mm": "telephoto compression, distant subject, strong bokeh",
    "macro": "extreme close-up, microscopic detail, shallow depth of field",
}

# Cinematic camera movements
FOCAL_PERSPECTIVE = {
    "dolly-in": "slow dolly in towards the subject, cinematic reveal",
    "dolly-out": "slow dolly out, revealing the wider scene",
    "pan-left": "smooth horizontal pan from right to left",
    "pan-right": "smooth horizontal pan from left to right",
    "tilt-up": "camera tilts upward, dramatic reveal of scale",
    "tilt-down": "camera tilts downward, focus narrows",
    "orbit": "camera orbits around the subject, dynamic movement",
    "crane-up": "camera rises vertically, epic perspective",
    "tracking": "camera tracks alongside the subject, parallel movement",
    "handheld": "natural handheld camera, slight organic shake",
    "static": "locked-off tripod, no movement, stable frame",
}


def format_error_message(err, fallback="Generation failed"):
    """Parse common MuAPI error formats into clean messages.

    Mirrors formatErrorMessage from packages/studio/src/utils/formatError.js.
    """
    if not err:
        return fallback
    if isinstance(err, str):
        message = err
    else:
        message = getattr(err, "message", None) or str(err) or fallback

    if "{" in message and "}" in message:
        try:
            json_start = message.index("{")
            data = json.loads(message[json_start:])
            for key in ("detail", "message"):
                if isinstance(data.get(key), str):
                    return data[key]
            nested = data.get("error", {})
            if isinstance(nested, dict) and isinstance(nested.get("message"), str):
                return nested["message"]
        except Exception:
            pass

    lower = message.lower()
    if "402" in message or "insufficient_credits" in lower or "insufficient credits" in lower:
        return "Insufficient credits. Please top up your wallet."
    if "401" in message or "403" in message:
        return "Authentication failed. Please check your account session or API key."
    if "429" in message:
        return "Too many requests. Please wait a moment and try again."

    message = re.sub(r"^API Request Failed: \d+ [^-]+ - ", "", message)
    return message[:150] + "..." if len(message) > 150 else message


def run(inputs):
    """
    Prompt enhancement + error formatting utility.

    inputs (one of):
        action="enhance" + base_prompt + style + lens + camera_movement
        action="quick_prompts" + category
        action="format_error" + error
        action="validate" + prompt

    returns:
        {"ok": True, "prompt": "..."} for enhance
        {"ok": True, "prompts": [...]} for quick_prompts
        {"ok": True, "error_message": "..."} for format_error
        {"ok": True, "valid": true, "issues": [...]} for validate
    """
    action = inputs.get("action") or "enhance"

    if action == "quick_prompts":
        return {
            "ok": True,
            "category": inputs.get("category") or "general",
            "prompts": QUICK_PROMPTS,
        }

    if action == "format_error":
        err = inputs.get("error")
        if err is None:
            return {"ok": False, "error": "error field required"}
        return {"ok": True, "error_message": format_error_message(err)}

    if action == "validate":
        prompt = inputs.get("prompt", "")
        issues = []
        if not prompt or not prompt.strip():
            issues.append("prompt is empty")
        if len(prompt) < 5:
            issues.append("prompt too short (< 5 chars)")
        if len(prompt) > 3000:
            issues.append("prompt too long (> 3000 chars)")
        return {
            "ok": True,
            "valid": len(issues) == 0,
            "issues": issues,
            "length": len(prompt),
        }

    if action == "enhance":
        base = inputs.get("base_prompt") or inputs.get("prompt", "")
        if not base:
            return {"ok": False, "error": "base_prompt or prompt required"}
        parts = [base]
        if inputs.get("style") and inputs["style"] in CAMERA_MAP:
            parts.append(CAMERA_MAP[inputs["style"]])
        if inputs.get("lens") and inputs["lens"] in LENS_MAP:
            parts.append(LENS_MAP[inputs["lens"]])
        if inputs.get("camera_movement") and inputs["camera_movement"] in FOCAL_PERSPECTIVE:
            parts.append(FOCAL_PERSPECTIVE[inputs["camera_movement"]])
        if inputs.get("lighting"):
            parts.append(f"lighting: {inputs['lighting']}")
        if inputs.get("mood"):
            parts.append(f"mood: {inputs['mood']}")
        if inputs.get("quality"):
            parts.append(f"quality: {inputs['quality']}")
        return {
            "ok": True,
            "prompt": ", ".join(parts),
            "added": [k for k in ("style", "lens", "camera_movement", "lighting",
                                 "mood", "quality") if inputs.get(k)],
        }

    return {"ok": False, "error": f"unknown action: {action} (use enhance, quick_prompts, format_error, validate)"}