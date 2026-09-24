# Runbook: LLM Provider Outage

## Symptoms

- All agent requests timing out or returning 5xx
- Langfuse dashboard shows zero LLM calls succeeding
- Error rate spike on `/chat` endpoint

## First 5 minutes

1. **Identify the failing provider**:
   ```bash
   # Check error distribution
   grep -c "provider=anthropic" /var/log/ai-empire/audit.log
   grep -c "provider=openai" /var/log/ai-empire/audit.log
   grep -c "provider=ollama" /var/log/ai-empire/audit.log

   # Test each provider manually
   curl -fsS http://localhost:11434/api/tags       # Ollama
   curl -fsS https://api.anthropic.com/v1/messages  # Claude (will 401 without key)
   ```

2. **Check status pages**:
   - Anthropic: https://status.anthropic.com
   - OpenAI: https://status.openai.com
   - Ollama: self-hosted, check `docker logs ai-empire-ollama`

## Mitigate

### If Ollama is down (we have GPU on site)

```bash
# Restart Ollama
docker compose --profile core restart ollama

# Check health
curl -fsS http://localhost:11434/api/tags

# If GPU crashed, check nvidia-smi
nvidia-smi
```

### If a cloud provider is down

The agent auto-falls-back via `LLMClient.detect()`. To force fallback:

```bash
# Force local Ollama for everyone
export OLLAMA_BASE_URL=http://localhost:11434
docker compose --profile core --profile agents restart langgraph-orchestrator
```

The `LLMClient` priority is: Ollama → LiteLLM → OpenAI → Anthropic.
With the cloud provider down, requests should already be falling back
to Ollama automatically.

### If LiteLLM proxy is down

```bash
docker compose --profile gateway restart litellm-proxy
# Bypass it temporarily
export LITELLM_URL=""  # back to direct provider calls
```

## Communicate

1. Post in `#incidents`: "LLM provider X down, falling back to Y"
2. Update status page if user-facing
3. Notify ops team

## After resolution

1. Confirm error rate is back to baseline
2. Check if any data was lost (failed jobs in audit_log)
3. Re-run any failed batch jobs
4. Post-mortem if duration > 1 hour
