"""
Empire Web UI server — uses the real LLM agent.
Streaming via WebSocket: tokens appear as the LLM generates them.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("empire.web")

app = FastAPI(title="AI Empire", version="2.0")


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse((Path(__file__).parent / "chat.html").read_text())


@app.get("/chat.html", response_class=HTMLResponse)
async def chat_html():
    return HTMLResponse((Path(__file__).parent / "chat.html").read_text())


@app.get("/health")
async def health():
    from empire.agent.llm_agent import agent
    backend = await agent.llm.detect()
    return {"status": "ok", "backend": backend}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    log.info("WebSocket connected")
    from empire.agent.llm_agent import agent
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                msg = {"text": data}
            text = msg.get("text", "").strip()
            thread_id = msg.get("thread_id", "ws")
            if not text:
                continue
            # Stream LLM response (real LLM, with tool calling)
            async for chunk in agent.stream(text, thread_id):
                await websocket.send_json(chunk)
    except Exception as e:
        log.exception("WebSocket error")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7777, log_level="info")
