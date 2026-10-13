# Runbook: LLM Cost Spike

## Alert
`EmpireLLMCostSpike` — Tenant spending > $50/hour

## Impact
Unexpected credit card bill; possible abuse.

## Diagnosis

1. **Identify which tenant/model is spiking**:
   ```bash
   curl -s http://prometheus:9090/api/v1/query?query=\
   topk\(10,+sum+by+\(tenant_id,+model\)+\
   \(rate\(empire_llm_cost_dollars_total\[1h\]\)\)\) | jq
   ```

2. **Check sessions for abuse**:
   ```bash
   psql -c "
     SELECT s.id, s.user_id, count(m.id) as msg_count
     FROM sessions s
     JOIN messages m ON m.session_id = s.id
     WHERE m.created_at > now() - interval '1 hour'
     GROUP BY s.id, s.user_id
     HAVING count(m.id) > 1000
     ORDER BY msg_count DESC;
   "
   ```

## Mitigation

1. **Lower rate limit for tenant** (immediate):
   ```bash
   redis-cli SET "rate_limit:tenant:$TENANT_ID:rpm" 5
   ```

2. **Force model downgrade** for tenant:
   ```bash
   # Update tenant settings in DB
   psql -c "UPDATE tenants SET tier='capped' WHERE id='$TENANT_ID';"
   ```

3. **Kill runaway session**:
   ```bash
   psql -c "UPDATE sessions SET status='terminated' WHERE id='$SESSION_ID';"
   ```

## Postmortem

Document the incident:
1. Root cause
2. Time to detect / mitigate / resolve
3. Action items
