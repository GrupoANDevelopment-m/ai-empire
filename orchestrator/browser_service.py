"""
Browser-Use service — HTTP wrapper around the browser-use library
Endpoints: /search /fill-form /click /extract /task
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
import asyncio
import os

app = FastAPI(title="Browser-Use Service", version="1.0.0")


class SearchRequest(BaseModel):
    query: str
    num_results: int = 10


class FillFormRequest(BaseModel):
    url: str
    fields: dict[str, str]
    submit: bool = False


class ClickRequest(BaseModel):
    url: str
    selector: str | None = None
    text: str | None = None


class ExtractRequest(BaseModel):
    url: str
    prompt: str


class TaskRequest(BaseModel):
    goal: str
    max_steps: int = 20


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/search")
async def search(req: SearchRequest):
    """Quick Google-like search using browser-use."""
    try:
        from browser_use import Agent
        from langchain_ollama import ChatOllama
        from langchain_anthropic import ChatAnthropic

        # Pick LLM
        if os.getenv("ANTHROPIC_API_KEY"):
            llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", api_key=os.getenv("ANTHROPIC_API_KEY"))
        elif os.getenv("OPENAI_API_KEY"):
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY"))
        else:
            llm = ChatOllama(model="llama3.3", base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"))

        agent = Agent(
            task=f"Search Google for '{req.query}'. Return the top {req.num_results} results as a JSON list with title, url, snippet.",
            llm=llm,
        )
        result = await agent.run()
        return {"results": result}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/fill-form")
async def fill_form(req: FillFormRequest):
    """Navigate to URL, fill form, optionally submit."""
    try:
        from browser_use import Agent
        from langchain_ollama import ChatOllama
        from langchain_anthropic import ChatAnthropic

        if os.getenv("ANTHROPIC_API_KEY"):
            llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", api_key=os.getenv("ANTHROPIC_API_KEY"))
        else:
            llm = ChatOllama(model="llama3.3", base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"))

        fields_str = ", ".join(f"{k}='{v}'" for k, v in req.fields.items())
        submit_str = "and submit the form" if req.submit else "do not submit"
        agent = Agent(
            task=f"Go to {req.url}. Fill in the form fields: {fields_str}. {submit_str}.",
            llm=llm,
        )
        result = await agent.run()
        return {"status": "submitted" if req.submit else "filled", "result": str(result)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/click")
async def click(req: ClickRequest):
    target = req.selector or f"button with text '{req.text}'"
    try:
        from browser_use import Agent
        from langchain_ollama import ChatOllama

        agent = Agent(
            task=f"Go to {req.url} and click on {target}.",
            llm=ChatOllama(model="llama3.3", base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")),
        )
        result = await agent.run()
        return {"status": "clicked", "result": str(result)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/extract")
async def extract(req: ExtractRequest):
    try:
        from browser_use import Agent
        from langchain_ollama import ChatOllama

        agent = Agent(
            task=f"Go to {req.url}. {req.prompt}. Return the result as JSON.",
            llm=ChatOllama(model="llama3.3", base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")),
        )
        result = await agent.run()
        return {"data": result}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/task")
async def generic_task(req: TaskRequest):
    try:
        from browser_use import Agent
        from langchain_ollama import ChatOllama
        from langchain_anthropic import ChatAnthropic

        if os.getenv("ANTHROPIC_API_KEY"):
            llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", api_key=os.getenv("ANTHROPIC_API_KEY"))
        else:
            llm = ChatOllama(model="llama3.3", base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"))

        agent = Agent(task=req.goal, llm=llm, max_steps=req.max_steps)
        result = await agent.run()
        return {"result": str(result), "history": getattr(agent, "history", [])}
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
