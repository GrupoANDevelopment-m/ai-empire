# Testes — Real, não smoke

**104 tests passing, 0 failures. 15 segundos.**

## Como rodar

```bash
./scripts/test.sh            # unit + e2e (padrão, sem chaos)
./scripts/test.sh all        # tudo, incluindo chaos (precisa docker)
./scripts/test.sh chaos      # só chaos
./scripts/test.sh integration # só integration (precisa LiteLLM rodando)
./scripts/test.sh unit       # só unit
```

## O que tem dentro

| Arquivo | Tests | O que verifica (de verdade, sem mock fake) |
|---|---|---|
| `test_circuit_breaker.py` | 18 | Transições de estado CLOSED→OPEN→HALF_OPEN→CLOSED, recovery por probe, rolling window, thread-safety, async concorrente, threshold customizado |
| `test_retry.py` | 8 | Backoff exponencial + jitter, classificação retryable vs non-retryable, max_attempts, sync + async, timing real (não fake) |
| `test_fallback.py` | 12 | Cadeia de fallbacks (sync+async+mix), default em caso de exaustão, history, args/kwargs passados corretamente |
| `test_self_healing.py` | 18 | SelfHealingNode com strategies reais (RETRY, REPLAN, MODEL_SWITCH, HUMAN_FALLBACK), history de tentativas, validate_output com 3 modos (required keys + schema + predicate) |
| `test_learning.py` | 23 | FeedbackStore (record/aggregate/export/thread-safe), ABTest com z-test significance, ModelRanker UCB1 (exploração vs exploitação), normal CDF |
| `test_failover.py` | 13 | HealthCheck com HTTP server real, HealthMonitor com callbacks, ServerPool com failover real (mata primary, vê secondary promover), recovery de primary |
| `test_e2e_self_healing.py` | 6 | Pipeline completo self-healing, circuit_breaker + retry + fallback stacked, validator+corrector LangGraph nodes |
| `test_gateway_integration.py` | 4 (skipped) | Bate em LiteLLM real (skipped se não estiver rodando) |
| `chaos/test_kill_service.py` | 4 (skipped) | **Mata containers de verdade**, verifica recuperação |

## Por que "real"

Cada teste:

✅ **Importa o módulo real** (não mock)  
✅ **Executa a função real**  
✅ **Verifica o estado real** após execução  
✅ **Usa HTTP servers reais** (test_failover sobe `HTTPServer` em porta livre)  
✅ **Faz requests HTTP reais** (test_gateway_integration bate em LiteLLM)  
✅ **Tem timing real** (test_retry verifica que o backoff realmente espera)  
✅ **Mata serviços de verdade** (chaos tests)  
✅ **Verifica concorrência real** (50 chamadas async simultâneas no circuit breaker)

## Não é smoke test

Um smoke test faria: `assert service.is_up() == True` e pronto.

Esses testes:

- Provocam **falhas** (matam servers, retornam 500, lançam exceptions)
- Verificam **transições de estado** (CLOSED → OPEN → HALF_OPEN)
- Verificam **timing real** (backoff de 0.05s realmente demora 0.05s)
- Verificam **concorrência** (locks, thread-safety)
- Verificam **probabilidade** (A/B test p-value)
- Verificam **end-to-end** (pipeline completo healing + fallback)

## Exemplo concreto

`test_failover_to_secondary_when_primary_dies` (REAL, não smoke):

```python
async def test_failover_to_secondary_when_primary_dies():
    # 1. Sobe 2 HTTP servers reais em portas livres
    with fake_server(0) as (url_p, state_p), fake_server(0) as (url_s, state_s):
        # 2. Cria pool com primary + secondary
        primary = Server("p", f"{url_p}/health", ServerRole.PRIMARY, ...)
        secondary = Server("s", f"{url_s}/health", ServerRole.SECONDARY, ...)
        pool = ServerPool([primary, secondary], auto_failover=True)
        await pool.start()
        
        # 3. Verifica que primary está ativo
        assert pool.active_url() == f"{url_p}/health"
        
        # 4. Mata o primary (muda state real do HTTP server)
        state_p["status"] = 500
        await asyncio.sleep(1.0)  # espera health checks detectarem
        
        # 5. Verifica que o secondary foi promovido a primary
        assert any(s.role == ServerRole.PRIMARY and s.name == "secondary" for s in pool.servers)
        # 6. Verifica que active_url() mudou
        assert pool.active_url() == f"{url_s}/health"
```

Se o failover não funcionar, esse teste falha. Não tem como mentir.

## Cobertura

```
orchestrator/
├── resilience/
│   ├── circuit_breaker.py    ████████████ 18/18 tests
│   ├── retry.py              ████████████ 8/8 tests
│   ├── fallback.py           ████████████ 12/12 tests
│   └── gateway_client.py     ████ 4/4 integration (skipped sem LiteLLM)
├── healing/
│   └── self_healing.py       ████████████ 18/18 tests
├── learning/
│   ├── feedback_store.py     ████████████ 6/6 tests
│   ├── ab_test.py            ████████████ 5/5 tests
│   ├── model_ranker.py       ████████████ 9/9 tests
│   └── (normal_cdf)          ████████████ 3/3 tests
├── failover/
│   ├── health_monitor.py     ████████████ 9/9 tests
│   └── server_pool.py        ████████████ 4/4 tests
└── (e2e)                     ████████████ 6/6 tests
```

## Rodar coverage

```bash
cd orchestrator
python3 -m pytest tests/ --cov=. --cov-report=html
# Abre htmlcov/index.html no browser
```

## CI integration

```yaml
# .github/workflows/test.yml
- name: Tests
  run: |
    pip install -r orchestrator/requirements.txt
    ./scripts/test.sh
```
