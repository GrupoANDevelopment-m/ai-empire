# AI Empire Runbooks

When something breaks, look here first. If the runbook doesn't help,
page on-call (see `docs/ONCALL.md`).

## Available runbooks

| Scenario | File |
|---|---|
| Incident triage | [01-incident-triage.md](01-incident-triage.md) |
| Service down (single service) | [02-service-down.md](02-service-down.md) |
| Postgres connection refused | [03-postgres-down.md](03-postgres-down.md) |
| LLM provider outage | [04-llm-outage.md](04-llm-outage.md) |
| PII leak suspected | [05-pii-leak.md](05-pii-leak.md) |
| Rollback a deployment | [06-rollback.md](06-rollback.md) |
| Secret rotation | [07-secret-rotation.md](07-secret-rotation.md) |
| Backup restore | [08-restore.md](08-restore.md) |
| Database migration failed | [09-migration-failed.md](09-migration-failed.md) |
| LLM costs spike | [10-cost-spike.md](10-cost-spike.md) |

## General incident response

1. **Acknowledge** the alert within 5 minutes (paging policy).
2. **Triage**: which service? what changed recently?
3. **Mitigate** first (stop the bleeding), then **investigate**.
4. **Communicate**: status page update every 30 minutes during incident.
5. **Post-mortem**: blameless writeup within 7 days.

## Escalation

| Severity | Examples | Response time | Escalation |
|---|---|---|---|
| **SEV-1** | total outage, PII leak | 15 min | CTO + DPO + Legal |
| **SEV-2** | single service down | 1 hour | on-call engineer |
| **SEV-3** | degraded performance | 4 hours | next business day |
| **SEV-4** | cosmetic / non-blocking | next sprint | backlog |
