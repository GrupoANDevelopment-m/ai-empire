"""
Empire Graph — state machine principal do LangGraph
Orquestra: plan → research → source_leads → qualify → design → outreach → publish → done
Com suporte a HITL (human-in-the-loop) antes de ações irreversíveis.
"""
from __future__ import annotations
from typing import Literal
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from state.schema import EmpireState
from tools.llm import get_llm
from tools.browser_use import browser_search, browser_fill_form, browser_click
from tools.searxng import web_search
from tools.crewai_tools import run_leads_crew, run_design_crew, run_outreach_crew
from nodes import plan, research, source_leads, qualify, design_content, outreach, publish, finalize, human_review


def build_empire_graph(checkpointer=None):
    """Compila o grafo principal. Em produção usar PostgresSaver."""
    if checkpointer is None:
        checkpointer = MemorySaver()

    g = StateGraph(EmpireState)

    # ---- Nodes ----
    g.add_node("plan", plan.run)
    g.add_node("research", research.run)
    g.add_node("source_leads", source_leads.run)
    g.add_node("qualify", qualify.run)
    g.add_node("design_content", design_content.run)
    g.add_node("outreach", outreach.run)
    g.add_node("publish", publish.run)
    g.add_node("human_review", human_review.run)
    g.add_node("finalize", finalize.run)

    # ---- Edges ----
    g.add_edge(START, "plan")

    g.add_conditional_edges(
        "plan",
        lambda s: "research" if s.goal else "finalize",
        {"research": "research", "finalize": "finalize"},
    )

    g.add_conditional_edges(
        "research",
        lambda s: "source_leads" if any(k in s.goal.lower() for k in ["lead", "venda", "prospec", "cliente"]) else "design_content",
        {"source_leads": "source_leads", "design_content": "design_content"},
    )

    g.add_edge("source_leads", "qualify")
    g.add_edge("qualify", "design_content")
    g.add_edge("design_content", "human_review")
    g.add_edge("outreach", "human_review")

    # Human review: aprova ou reprova
    g.add_conditional_edges(
        "human_review",
        lambda s: "publish" if s.human_decision and s.human_decision.get("approved") else "design_content",
        {"publish": "publish", "design_content": "design_content"},
    )

    g.add_edge("publish", "outreach")
    g.add_conditional_edges(
        "outreach",
        lambda s: "finalize" if len(s.published) >= 1 else "human_review",
        {"finalize": "finalize", "human_review": "human_review"},
    )

    g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer)
