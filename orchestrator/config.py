"""AI Empire — configuration"""
from __future__ import annotations
import os
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: Literal["ollama", "anthropic", "openai"] = "ollama"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.3"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    browser_use_api_key: str = ""

    # Database
    database_url: str = "postgresql://empire:empire_dev@postgres:5432/ai_empire"
    redis_url: str = "redis://redis:6379/0"

    # Observability
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langchain_tracing: bool = False

    # Active profiles (informational)
    active_profiles: list[str] = ["core", "agents"]

    # Service endpoints
    n8n_url: str = "http://n8n:5678"
    qdrant_url: str = "http://qdrant:6333"
    searxng_url: str = "http://searxng:8080"
    comfyui_url: str = "http://comfyui:8188"
    penpot_url: str = "http://penpot:9001"
    browser_use_url: str = "http://browser-use:8001"
    chatwoot_url: str = "http://chatwoot:3000"
    open_sora_url: str = "http://open-sora:8003"
    whisper_url: str = "http://whisper:9000"
    crawl4ai_url: str = "http://crawl4ai:8000"

    def effective_model(self) -> str:
        if self.llm_provider == "ollama":
            return f"ollama/{self.ollama_model}"
        if self.llm_provider == "anthropic":
            return "claude-sonnet-4.5"
        return "gpt-4o"


settings = Settings()
