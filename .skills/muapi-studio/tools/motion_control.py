"""Motion control — transfer motion from a reference video to new characters/assets.

Mirrors MotionControlStudio (processMotionControl). Two modes:
- motion_transfer: extract motion from reference video, apply to new characters
- objects_swap: swap characters/products/clothes in a video, keep the rest
"""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Apply motion transfer or object swap to a video.

    inputs:
        video_url (str): required — source/reference video with the choreography
        prompt (str): optional override of the internal prompt
        mode (str): "motion_transfer" (default) or "objects_swap"
        images_list (list): reference images of new characters/assets (up to 30)
        image_url (str): convenience for single-image mode
        aspect_ratio (str): "16:9" (default), "9:16", "1:1", "4:3", "3:4", "21:9"
        duration (int): seconds (default 5, max ~30)
        generate_audio (bool): include audio (default False)
        seed (int): -1 for random
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    video_url = inputs.get("video_url")
    if not video_url:
        return {"ok": False, "error": "video_url required"}

    mode = inputs.get("mode") or "motion_transfer"
    internal_prompt = (
        "Keep the rest of the scene as filmed, swap the characters, products, or clothes with the reference images."
        if mode == "objects_swap"
        else "Extract motion from the reference video and rebuild the scene with the new characters and assets, preserving the original motion, choreography, and camera movements."
    )

    user_prompt = str(inputs.get("prompt") or "").strip()
    final_prompt = f"{internal_prompt} {user_prompt}" if user_prompt else internal_prompt

    # Image references
    images_list = []
    if isinstance(inputs.get("images_list"), list):
        images_list = inputs["images_list"]
    elif inputs.get("images"):
        imgs = inputs["images"]
        images_list = imgs if isinstance(imgs, list) else [imgs]
    elif inputs.get("image_url"):
        images_list = [inputs["image_url"]]

    if not images_list:
        return {"ok": False, "error": "image_url or images_list required (the characters/assets to apply)"}

    payload = {
        "video_url": video_url,
        "images_list": images_list,
        "aspect_ratio": inputs.get("aspect_ratio") or "16:9",
        "duration": int(inputs.get("duration") or 5),
        "generate_audio": bool(inputs.get("generate_audio")),
        "prompt": final_prompt,
    }
    if inputs.get("seed") and int(inputs["seed"]) != -1:
        payload["seed"] = int(inputs["seed"])

    result = request("POST", "/api/v1/seedance-2.5-motion-control",
                    body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        return {"ok": True, "url": extract_output_url(submit), "sync": True}

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted"}

    polled = poll_result(request_id,
                         int(inputs.get("poll_max_attempts") or 150),
                         int(inputs.get("poll_interval_ms") or 3000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": request_id,
        "url": extract_output_url(polled["data"]),
        "mode": mode,
        "duration": payload["duration"],
    }