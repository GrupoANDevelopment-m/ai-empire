"""
Empire State — schema global do LangGraph
Modela o estado de uma execução do agente do início ao fim
"""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    role: str = ""
    linkedin_url: str = ""
    website: str = ""
    status: Literal["new", "qualified", "outreach", "engaged", "meeting", "won", "lost"] = "new"
    score: int = 0
    metadata: dict[str, Any] = {}


class ContentItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: Literal["text", "image", "video", "carousel", "post", "email", "dm"] = "text"
    title: str = ""
    body: str = ""
    media_url: str = ""
    channels: list[str] = []
    status: Literal["draft", "review", "approved", "published"] = "draft"
    scheduled_for: datetime | None = None


class ResearchNote(BaseModel):
    query: str
    summary: str
    sources: list[str] = []
    insights: list[str] = []


class EmpireState(BaseModel):
    """Estado global de uma execução."""
    # Identificação
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = ""
    user_id: str = "default"

    # Pipeline de leads
    leads: list[Lead] = []
    current_lead_id: str | None = None

    # Conteúdo gerado
    content_queue: list[ContentItem] = []
    published: list[ContentItem] = []

    # Research
    research_notes: list[ResearchNote] = []

    # Controle
    current_step: str = "start"
    next_action: str | None = None
    awaiting_human: bool = False
    human_decision: dict[str, Any] | None = None

    # Erros e logs
    errors: list[str] = []
    logs: list[str] = []

    # Output final
    output: dict[str, Any] = {}

    # Métricas
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    tokens_used: int = 0
