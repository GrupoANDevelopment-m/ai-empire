-- AI Empire — Postgres schema
-- Idempotent. Run on first container startup.

CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUIDs
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- encrypted columns

-- ── Approvals (HITL) ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS approvals (
    id           UUID PRIMARY KEY,
    tenant       TEXT NOT NULL,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    target       TEXT,
    args         JSONB NOT NULL,
    created_at   DOUBLE PRECISION NOT NULL,
    expires_at   DOUBLE PRECISION NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','expired','auto_approved')),
    decided_by   TEXT,
    decided_at   DOUBLE PRECISION,
    result       JSONB
);
CREATE INDEX IF NOT EXISTS idx_approvals_tenant_status ON approvals(tenant, status);
CREATE INDEX IF NOT EXISTS idx_approvals_expires ON approvals(expires_at) WHERE status = 'pending';

-- ── Audit log (immutable, append-only) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id   UUID NOT NULL,
    tenant       TEXT NOT NULL,
    actor        TEXT NOT NULL,
    role         TEXT NOT NULL,
    action       TEXT NOT NULL,
    target       TEXT,
    ok           BOOLEAN NOT NULL,
    error        TEXT,
    args         JSONB,
    result_summary TEXT,
    ip           INET,
    user_agent   TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON audit_log(tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, ts DESC);

-- Audit log is append-only (defense in depth)
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
CREATE OR REPLACE FUNCTION prevent_audit_modification() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_immutable ON audit_log;
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- ── API keys (hashed) ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant        TEXT NOT NULL,
    label         TEXT NOT NULL,
    key_hash      TEXT NOT NULL UNIQUE,        -- bcrypt of the key
    key_prefix    TEXT NOT NULL,              -- first 8 chars for display
    role          TEXT NOT NULL CHECK (role IN ('admin','operator','viewer','agent')),
    scope         TEXT[] NOT NULL DEFAULT '{}',
    created_by    TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ,
    expires_at    TIMESTAMPTZ,
    revoked_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant) WHERE revoked_at IS NULL;

-- ── LLM cost tracking ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS llm_usage (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant       TEXT NOT NULL,
    actor        TEXT NOT NULL,
    provider     TEXT NOT NULL,    -- 'ollama', 'anthropic', 'openai', 'litellm'
    model        TEXT NOT NULL,
    prompt_tokens    INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens  INT NOT NULL DEFAULT 0,
    cost_usd     NUMERIC(10,6) NOT NULL DEFAULT 0,
    latency_ms   INT,
    session_id   TEXT,
    tool_call    TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_tenant_ts ON llm_usage(tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_actor ON llm_usage(actor, ts DESC);

-- ── Conversation state (LangGraph checkpoints) ─────────────────────────────
-- Schema managed by langgraph.checkpoint.postgres on first run.
-- We only seed a comment so the table isn't lost.

COMMENT ON DATABASE ai_empire IS 'AI Empire — created by install.sh';
