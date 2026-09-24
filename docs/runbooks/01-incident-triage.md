# Runbook: Incident Triage

## First 5 minutes

1. **Acknowledge** the page.
2. **Check the status page** — is this already known?
3. **Open the dashboard**: Grafana → "Empire Overview".
4. **Identify the failing service** from the alert and locate the
   relevant runbook in `docs/runbooks/`.

## Triage checklist

- [ ] What service / endpoint is affected?
- [ ] When did it start? (check `docker compose ps --format json`)
- [ ] What changed? (check git log, recent deploys, env changes)
- [ ] Is it a single tenant or all tenants?
- [ ] Is data at risk? (writes failing?)
- [ ] Is it a security incident? (PII leak, unauthorized access)

## Quick checks

```bash
# All containers
docker compose ps

# Healthcheck status
docker compose ps --format json | jq '.[] | select(.Health != "healthy")'

# Recent logs (last 100 lines, all services)
docker compose logs --tail=100 --no-color

# Resource usage
docker stats --no-stream

# Disk space
df -h
du -sh /var/lib/docker/volumes/*

# Postgres connectivity
docker exec ai-empire-postgres pg_isready -U empire
```

## Decide severity

| Symptom | Severity |
|---|---|
| Total outage | SEV-1 |
| One service down, others compensate | SEV-2 |
| Slow responses, no errors | SEV-3 |
| Cosmetic / single user | SEV-4 |

## Communicate

1. Update `#incidents` Slack channel.
2. Update status page (`status.ai-empire.dev`).
3. Notify affected customers via email if SEV-1/2.

## After resolution

1. Mark incident resolved in PagerDuty / OpsGenie.
2. Schedule post-mortem within 7 days.
3. File follow-up tickets for prevention.
