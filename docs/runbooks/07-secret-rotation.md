# Runbook: Secret Rotation

When a secret needs to be rotated (routine, breach, or employee offboarding):

## Prerequisites

- New secret value (32+ random chars, generated with `openssl rand -hex 32`)
- Access to `.env` and to all running containers

## Steps

### 1. Postgres password

```bash
# Generate new password
NEW_PG=$(openssl rand -hex 32)

# Update .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$NEW_PG/" .env

# Update postgres user
docker exec -u postgres ai-empire-postgres \
    psql -c "ALTER USER empire PASSWORD '$NEW_PG';"

# Restart all services that connect to postgres
docker compose --profile core --profile agents --profile crm restart
```

### 2. Redis password (if set)

```bash
NEW_REDIS=$(openssl rand -hex 32)
sed -i "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$NEW_REDIS/" .env
# Update redis requirepass (if enabled)
docker exec ai-empire-redis redis-cli CONFIG SET requirepass "$NEW_REDIS"
docker compose --profile core restart langgraph-orchestrator worker
```

### 3. JWT_SECRET / SECRET_KEY

This invalidates ALL existing tokens — every user must re-login.

```bash
NEW_SECRET=$(openssl rand -hex 32)
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" .env
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$NEW_SECRET/" .env
docker compose --profile core --profile agents restart langgraph-orchestrator web
```

### 4. LLM provider keys

Anthropic / OpenAI keys — rotate from the provider's dashboard, then update `.env`:

```bash
sed -i "s/^ANTHROPIC_API_KEY=.*/ANTHROPIC_API_KEY=$NEW_KEY/" .env
docker compose --profile core --profile agents restart
```

### 5. n8n basic auth

```bash
NEW_N8N=$(openssl rand -hex 32)
sed -i "s/^N8N_BASIC_AUTH_PASSWORD=.*/N8N_BASIC_AUTH_PASSWORD=$NEW_N8N/" .env
docker compose --profile core restart n8n
```

### 6. API keys for users

For each user, generate a new key, revoke the old one:

```bash
python -c "
import secrets
print('emp_' + secrets.token_urlsafe(32))
"

# Revoke old in DB
psql -c "UPDATE api_keys SET revoked_at = now() WHERE key_prefix = 'OLD_PREFIX';"
```

## Verify

```bash
# Postgres
docker exec ai-empire-postgres pg_isready -U empire

# Agent API
curl -fsS http://localhost:8123/health

# Re-authenticate to test new tokens
curl -fsS -H "Authorization: Bearer $NEW_TOKEN" http://localhost:8123/whoami
```

## Audit

Log to incident tracker:
- Date/time of rotation
- Who authorized it
- Old value (last 4 chars only) + new value (last 4 chars only)
- Reason for rotation
