# AI Empire — Production Gates

Three gates must be passed before external exposure. Each gate has explicit
acceptance criteria; do not skip.

---

## Gate 0 — Before any external exposure

**Status (this commit): 7/9 done, 2/9 partial.**

| # | Item | Status | Where |
|---|---|---|---|
| 1 | **Authentication on every API endpoint** | ✓ | `empire/security/auth.py` (JWT HS256) |
| 2 | **RBAC (admin / operator / viewer / agent)** | ✓ | `empire/security/rbac.py` |
| 3 | **Tenant isolation** | ⚠ partial | Postgres schema-based isolation in migrations, no enforcement in agent loop yet |
| 4 | **Rate limit per API key and per tenant** | ✓ | `empire/security/rate_limit.py` (Redis Lua token bucket) |
| 5 | **No default secrets in compose** | ✓ | `.env.example` is empty values only; secrets generated on first install |
| 6 | **No internal ports exposed externally** | ⚠ partial | Caddy reverse proxy config added, but `docker-compose.yml` still has host-port mappings (operator must set `internal_only: true` profile) |
| 7 | **State persisted in Postgres/Redis** | ✓ | LangGraph `PostgresSaver`, sessions in Postgres, audit in Postgres |
| 8 | **HITL approval flow (real, not stub)** | ✓ | `orchestrator/hitl.py` + `approvals_api.py` |
| 9 | **PII policy, retention, opt-out** | ✓ | `empire/security/pii.py` + `docs/PII.md` (see below) |
| 10 | **CI minimum** | ✓ | `.github/workflows/ci.yml` (lint, tests, compose, security, build) |
| 11 | **Image digests pinned** | ⚠ partial | digests NOT pinned in compose (use specific tags like `:2.11-alpine`). Full SHA256 pinning is recommended for air-gapped deploys |

### PII policy (Gate 0.9)

All PII (email, phone, credit card, SSN, IBAN, IPv4) is redacted before
audit logging. Configurable via `PII_REDACT` env var.

Retention: `PII_RETENTION_DAYS=30` — auto-delete conversation logs after N days.

Opt-out: every API request can include `X-No-PII-Log: true` to skip logging.

See `docs/PII.md` for the full policy (DPO contact, data subject rights, breach response).

---

## Gate 1 — Production intern control

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | `docker compose config -q` passes | ✓ | `.github/workflows/ci.yml::compose` runs this for every profile |
| 2 | All images `docker pull` successfully | ✓ | `scripts/verify_images.sh` checks each one against the registry |
| 3 | Migrations run for every service with DB | ✓ | `orchestrator/migrations/001_init.sql` + per-service migration jobs in compose |
| 4 | Backup tested for Postgres, Redis, Qdrant | ✓ | `scripts/backup.sh` (cron), `scripts/restore.sh` (manual, requires confirmation) |
| 5 | Observability: logs, metrics, traces | ✓ | `structlog` for JSON logs, OTEL hooks, Langfuse for LLM traces |
| 6 | Runbooks for incident, rollback, secret rotation | ✓ | `docs/runbooks/` (5 documents) |
| 7 | Staging environment separate from prod | ⚠ TODO | `docker-compose.staging.yml` (not yet written) |
| 8 | Healthchecks real for every service | ✓ | `healthcheck:` blocks in compose for 12 services |
| 9 | Build of all custom Dockerfiles | ✓ | `.github/workflows/ci.yml::build` |

---

## Gate 2 — Multi-user / commercial product

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Billing / quotas / cost cap per tenant | ✓ | `llm_usage` table + `RATE_LIMIT_AGENT=20/min` |
| 2 | Audit trail of all actions + approvals | ✓ | `audit_log` table (immutable trigger), `approvals` table |
| 3 | Load testing (≥ 100 RPS, p99 < 2s) | ⚠ TODO | use `locust` or `k6` |
| 4 | Security audit (pen-test report) | ⚠ TODO | external pen-test before launch |
| 5 | Recovery drill (kill a node, measure RTO) | ⚠ TODO | quarterly drill |
| 6 | Prompt / model / tool versioning | ✓ | prompts in `config/prompts/`, model pins in `config/litellm/config.yaml` |
| 7 | DPA (Data Processing Agreement) | ⚠ TODO | legal template |
| 8 | SLOs defined and measured | ✓ | `docs/SLOS.md` |
| 9 | Privacy policy + opt-out flow | ⚠ TODO | legal + UI |

---

## How to verify Gate 0 before going live

```bash
# 1. Run the audit script
./scripts/verify_images.sh docker-compose.yml   # all images exist

# 2. Validate compose syntax for each profile
for p in core agents browser leads design video data crm office gateway lite; do
    docker compose --profile $p config -q
done

# 3. Run the test suite
./empire test all

# 4. Run CI locally
act -j lint tests security   # requires `act` CLI

# 5. Smoke test auth + RBAC
python -c "
import os
os.environ['SECRET_KEY'] = 'x' * 64
from empire.security.auth import issue_token, verify_token
from empire.security.rbac import has_permission, AuthContext, Permission, Role
t = issue_token('admin', Role.ADMIN, 'tenant1')
assert verify_token(t)['role'] == 'admin'
assert has_permission(AuthContext('u', Role.OPERATOR, 't'), Permission.RUN_TESTS)
print('all checks pass')
"

# 6. Verify backup works
./scripts/backup.sh postgres
./scripts/restore.sh postgres /var/backups/ai-empire/LATEST-postgres.sql.gz
```

If all 6 pass, you're at Gate 0.

---

## Known gaps (honest list)

These are the items marked ⚠ in the tables above. They are real gaps that
need to be closed before commercial launch:

1. **Tenant isolation enforcement in agent loop** — `TenantContext` is
   plumbed through JWT and audit log, but the agent loop does not yet
   enforce that one tenant's leads/sessions are not visible to another.
   Need to add `WHERE tenant = $auth.tenant` to every DB query.

2. **Internal-only profile** — operator must manually switch to a profile
   that does not publish container ports to the host. Compose currently
   exposes ports; need `profiles: [internal-only]` overlay.

3. **Image digest pinning** — for true reproducibility/air-gapped, every
   `image:` should be pinned to `image@sha256:digest...`. Recommend
   running `docker pull` once and capturing digests.

4. **Staging environment** — `docker-compose.staging.yml` not yet created.

5. **Load testing, security audit, recovery drill, DPA, privacy policy** —
   these are human-in-the-loop activities that cannot be done in code.

---

## Closing checklist

- [ ] Tenant isolation enforced in code (not just schema)
- [ ] Internal-only profile in compose
- [ ] Image digests pinned
- [ ] Staging compose file
- [ ] External pen-test
- [ ] DPA + privacy policy
- [ ] Quarterly recovery drill
