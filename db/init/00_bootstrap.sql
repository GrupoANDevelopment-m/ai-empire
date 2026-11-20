-- AI Empire — database bootstrap
--
-- Runs automatically when the Postgres container initialises an empty
-- data directory (mounted at /docker-entrypoint-initdb.d).
--
-- The application schema itself is owned by Alembic
-- (db/migrations/, applied with `alembic upgrade head`). This file only
-- sets up what must exist before migrations run and what protects the
-- audit trail afterwards.

-- pgcrypto: gen_random_uuid() and digest() for the append-only guard.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- A dedicated schema for audit records keeps the append-only trigger
-- out of the way of regular migrations.
CREATE SCHEMA IF NOT EXISTS audit;

-- Append-only guard: the audit log may be inserted into and never
-- updated or deleted. This is enforced by the database, not by
-- application code, so a bug in the app cannot rewrite history.
CREATE OR REPLACE FUNCTION audit.prevent_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is append-only: % on audit_log is not permitted',
        TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'audit' AND tablename = 'audit_log'
    ) THEN
        CREATE TABLE audit.audit_log (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
            request_id  TEXT,
            tenant      TEXT NOT NULL,
            actor       TEXT,
            role        TEXT,
            action      TEXT NOT NULL,
            target      TEXT,
            ok          BOOLEAN NOT NULL DEFAULT TRUE,
            error       TEXT,
            args        JSONB,
            result_summary TEXT,
            ip          TEXT,
            user_agent  TEXT
        );
        CREATE INDEX audit_log_ts_idx    ON audit.audit_log (ts DESC);
        CREATE INDEX audit_log_tenant_idx ON audit.audit_log (tenant, ts DESC);
        CREATE INDEX audit_log_action_idx ON audit.audit_log (action);

        CREATE TRIGGER audit_log_append_only
            BEFORE UPDATE OR DELETE ON audit.audit_log
            FOR EACH ROW EXECUTE FUNCTION audit.prevent_mutation();
    END IF;
END;
$$;

-- The tenant that the seed file expects.
INSERT INTO tenants (id, name, slug, tier, max_skills, max_tools,
                     max_files, max_file_size, api_calls_per_minute)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Grupo AN', 'grupo-an', 'enterprise',
    100, 1000, 100, 10485760000, 600
)
ON CONFLICT (id) DO NOTHING;
