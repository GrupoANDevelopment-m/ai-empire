"""
Structured logging + OpenTelemetry hooks.

Production deployments must:
  - Emit JSON logs (structlog)
  - Export traces to OTEL-compatible backend
  - Track LLM cost + token usage in Postgres (llm_usage)
"""
import os
import sys
import time
import logging
import json
from contextlib import contextmanager
from typing import Any, Optional

import structlog


def configure_logging():
    """Configure structlog for JSON output to stdout."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger("empire")


@contextmanager
def traced_operation(name: str, **attrs):
    """Simple span for tracking operation latency."""
    start = time.time()
    log.info("operation.start", op=name, **attrs)
    try:
        yield
    except Exception as e:
        log.error("operation.error", op=name, error=str(e), **attrs)
        raise
    finally:
        elapsed_ms = int((time.time() - start) * 1000)
        log.info("operation.end", op=name, elapsed_ms=elapsed_ms, **attrs)


def record_llm_usage(tenant: str, actor: str, provider: str, model: str,
                      prompt_tokens: int = 0, completion_tokens: int = 0,
                      latency_ms: int = 0, session_id: str = "",
                      tool_call: str = "") -> None:
    """
    Record LLM token usage and cost to Postgres.
    Cost is computed from a static price table — update as pricing changes.
    """
    # Static price table (USD per 1K tokens) — update from provider pages
    PRICES = {
        ("anthropic", "claude-sonnet-4-5"):   (0.003, 0.015),
        ("anthropic", "claude-haiku-4-5"):    (0.0008, 0.004),
        ("openai",    "gpt-4o-mini"):         (0.00015, 0.0006),
        ("openai",    "gpt-4o"):              (0.0025, 0.01),
        ("ollama",    "qwen2.5:0.5b"):        (0.0, 0.0),     # local, free
        ("ollama",    "qwen2.5:3b"):          (0.0, 0.0),
        ("ollama",    "qwen2.5:7b"):          (0.0, 0.0),
    }
    prompt_price, completion_price = PRICES.get((provider, model), (0.0, 0.0))
    cost = (prompt_tokens / 1000 * prompt_price) + (completion_tokens / 1000 * completion_price)

    log.info("llm.usage",
             tenant=tenant, actor=actor, provider=provider, model=model,
             prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
             latency_ms=latency_ms, cost_usd=round(cost, 6),
             session_id=session_id, tool_call=tool_call)

    # Persist to Postgres (best effort)
    try:
        import asyncpg
        dsn = os.getenv("DATABASE_URL", "postgresql://empire:empire@postgres:5432/ai_empire")
        async def _insert():
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute(
                    """INSERT INTO llm_usage
                       (tenant, actor, provider, model, prompt_tokens,
                        completion_tokens, total_tokens, cost_usd,
                        latency_ms, session_id, tool_call)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                    tenant, actor, provider, model, prompt_tokens,
                    completion_tokens, prompt_tokens + completion_tokens,
                    cost, latency_ms, session_id, tool_call,
                )
            finally:
                await conn.close()
        # Best effort — don't block the request
        import asyncio
        try:
            asyncio.get_event_loop().create_task(_insert())
        except RuntimeError:
            pass  # no loop, skip
    except Exception:
        pass  # logging best-effort


def emit_metric(name: str, value: float, tags: dict[str, str] | None = None) -> None:
    """Emit a metric to logs (OTEL exporter picks up)."""
    log.info("metric", name=name, value=value, tags=tags or {})
