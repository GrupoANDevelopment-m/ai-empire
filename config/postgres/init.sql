-- AI Empire — Postgres init script
-- Runs on first container startup. Creates databases for every service that needs one.

CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID generation

-- Main app database
-- (already created by POSTGRES_DB env var, but explicit for clarity)

-- Langfuse (LLM observability)
CREATE DATABASE langfuse;

-- OpenOutreach (LinkedIn automation)
CREATE DATABASE openoutreach;

-- Twenty CRM
CREATE DATABASE twenty;

-- Cal.com (scheduling)
CREATE DATABASE calcom;

-- Baserow (Airtable alternative)
CREATE DATABASE baserow;

-- Chatwoot (omni-channel inbox)
CREATE DATABASE chatwoot;

-- Permissions (already done by POSTGRES_USER, but explicit for clarity)
GRANT ALL PRIVILEGES ON DATABASE langfuse TO empire;
GRANT ALL PRIVILEGES ON DATABASE openoutreach TO empire;
GRANT ALL PRIVILEGES ON DATABASE twenty TO empire;
GRANT ALL PRIVILEGES ON DATABASE calcom TO empire;
GRANT ALL PRIVILEGES ON DATABASE baserow TO empire;
GRANT ALL PRIVILEGES ON DATABASE chatwoot TO empire;
