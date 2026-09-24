# AI Empire — SLOs & SLIs (Service Level Objectives / Indicators)

These are the targets for production deployments. Adjust per customer contract.

## SLIs (what we measure)

| Indicator | Source | Formula |
|---|---|---|
| **Availability** | uptime probe | (successful healthchecks / total healthchecks) over 30d |
| **Latency (p50/p95/p99)** | nginx/Caddy access logs | percentile of HTTP response times |
| **Error rate** | same logs | 5xx / total requests |
| **Job success rate** | worker audit | jobs.completed / jobs.started |
| **Tool call latency** | Langfuse | percentile of tool spans |
| **LLM call success** | Langfuse | non-error responses / total LLM calls |
| **Cost per task** | llm_usage table | avg(USD) per completed task |
| **Token throughput** | llm_usage | total_tokens / elapsed_seconds |
| **PII leak events** | audit log scan | grep for known PII patterns in outbound |
| **HITL approval latency** | approvals table | avg(expires_at - decided_at) |

## SLOs (targets)

| Service | Availability | p99 latency | Error rate | Notes |
|---|---|---|---|---|
| LangGraph API | 99.5% | < 2s | < 1% | excludes upstream LLM latency |
| Web UI | 99.5% | < 1s | < 1% | |
| ComfyUI | 99.0% | < 60s/image | < 5% | image gen, slower |
| Browser-use | 98.0% | < 90s/task | < 10% | browser automation flaky |
| CrewAI leads | 95.0% | < 5min/batch | < 5% | batch job |
| Postgres | 99.9% | < 50ms | < 0.1% | |
| Redis | 99.9% | < 5ms | < 0.1% | |
| n8n | 99.0% | < 10s | < 2% | workflow execution |

**Error budget:** 0.5% / month for core. Burn rate alerts:
- 2% budget consumed in 1h → page
- 10% in 24h → ticket

## RTO / RPO

| Service | RTO (Recovery Time Objective) | RPO (Recovery Point Objective) |
|---|---|---|
| Postgres | < 15 min | < 1 hour (15-min backup cadence) |
| Redis | < 5 min | < 5 min (snapshot) |
| Qdrant | < 30 min | < 24 hours (nightly) |
| Volume data | < 1 hour | < 24 hours |

## Cost SLOs

| Tier | Monthly LLM spend cap | Hard actions on breach |
|---|---|---|
| **Trial** | $5 | disable new sessions |
| **Pro** | $50 | notify admin, soft cap |
| **Enterprise** | custom | per-contract |

## Alerting rules (Prometheus-style)

```yaml
- alert: EmpireHighErrorRate
  expr: rate(empire_http_5xx_total[5m]) > 0.05
  for: 5m
  severity: page

- alert: EmpireSlowLLM
  expr: histogram_quantile(0.99, rate(empire_llm_latency_ms_bucket[5m])) > 30000
  for: 10m
  severity: warn

- alert: EmpirePIILeak
  expr: increase(empire_pii_redactions_total[5m]) > 100
  for: 1m
  severity: page

- alert: EmpireBudgetBurn
  expr: rate(empire_llm_cost_usd_total[1h]) > 5
  for: 1h
  severity: warn
```

## Compliance / regulatory

- **GDPR** — EU customers: PII must be deletable on request, audit log must show who accessed what.
- **HIPAA** — US healthcare: PHI redaction required, BAA with LLM providers.
- **SOC 2** — audit log retention >= 1 year, immutable storage.
- **EU AI Act** — transparency for AI-generated content, log model + prompt for each output.

## Measurement cadence

| Frequency | Action |
|---|---|
| Real-time | healthchecks, rate limits |
| 1 min | error rate, latency p99 |
| 1 hour | token spend, HITL approval latency |
| 1 day | availability, backup integrity, PII scan |
| 1 week | cost review, capacity planning |
| 1 month | SLO review, error budget reset |
