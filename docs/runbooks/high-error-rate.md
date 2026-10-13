# Runbook: High Error Rate

## Alert
`EmpireHighErrorRate` — 5xx rate > 5% for 5 minutes

## Impact
Users see failed requests; LLM/tool calls fail.

## Diagnosis

1. **Check error breakdown**:
   ```bash
   curl -s http://prometheus:9090/api/v1/query?query=sum+by\(status\)+\
   \(rate\(empire_requests_total\[5m\]\)\) | jq
   ```

2. **Check LLM provider health**:
   ```bash
   curl -s http://localhost:8080/health | jq .components.llm
   ```

3. **Check external services**:
   - NVIDIA NIM: `curl https://integrate.api.nvidia.com/v1/models -H "Authorization: Bearer $KEY"`
   - Postgres: `psql -c "SELECT 1"`
   - Redis: `redis-cli ping`

## Mitigation

1. **If LLM is down** — switch provider in `.env`:
   ```bash
   NVIDIA_NIM_API_KEY=""  # disable
   OPENAI_API_KEY="sk-..."  # enable fallback
   kubectl rollout restart deploy/ai-empire
   ```

2. **If Postgres is slow** — check for long queries:
   ```sql
   SELECT pid, now() - query_start AS duration, query
   FROM pg_stat_activity
   WHERE state = 'active'
   ORDER BY duration DESC
   LIMIT 10;
   ```

3. **If Redis is full** — increase maxmemory:
   ```bash
   redis-cli CONFIG SET maxmemory 4gb
   redis-cli CONFIG SET maxmemory-policy allkeys-lru
   ```

## Rollback

```bash
# Roll back to previous deployment
kubectl rollout undo deploy/ai-empire
```
