# ADR-0001: Use LangGraph for State Machine

## Status
Accepted — 2026-01-15

## Context
We need a way to orchestrate complex agent workflows with branching, retry,
human-in-the-loop checkpoints, and persistence. Options considered:
1. LangGraph (Python) — graph-based, with built-in checkpointing
2. CrewAI (Python) — role-based, simpler
3. Custom state machine (Python) — full control, more code
4. Temporal (Go) — battle-tested, but requires new language/runtime

## Decision
Use **LangGraph** for the orchestration layer.

## Rationale
- Native Python — same language as the rest of the platform
- Built-in checkpointing with PostgresSaver
- Easy HITL with `interrupt_before` / `interrupt_after`
- Used in production by Klarna, Replit, Elastic
- Type-safe state with TypedDict
- Can be combined with CrewAI for role-based delegation

## Consequences
**Positive:**
- Less code to maintain
- Industry-standard patterns
- Easy to add new node types

**Negative:**
- Adds dependency (~50MB)
- Less control over low-level execution
- State schema changes can be tricky to migrate

## Alternatives Considered
- **CrewAI**: Simpler but limited HITL support
- **Custom state machine**: Too much code for too little gain
- **Temporal**: Different language, different deployment model
