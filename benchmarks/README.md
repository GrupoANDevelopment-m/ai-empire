# AI Empire — Load testing & benchmarking

Two tools:
- **Locust** (Python) — full-featured, Web UI, distributed mode
- **k6** (Go) — fast smoke test, CI-friendly

Both validate against SLOs defined in `docs/SLOS.md`.

## Quick start

### Locust (full)

```bash
# Install
pip install locust

# Run headless (CI / one-shot)
./benchmarks/run-benchmark.sh http://localhost:8123

# Run with Web UI (interactive)
locust -f benchmarks/locustfile.py --host=http://localhost:8123
# Open http://localhost:8089
```

### k6 (smoke, CI)

```bash
# Install
brew install k6      # macOS
# or: apt-get install k6

# Run
k6 run benchmarks/k6-smoke.js

# With env
HOST=https://staging.your-empire.example.com \
TOKEN=$REAL_JWT \
k6 run --out json=results.json benchmarks/k6-smoke.js
```

## Scenarios

`benchmarks/locustfile.py` defines 3 user types:

| Type | Weight | Behavior |
|---|---|---|
| `EmpireUser`     | 70% | Normal user. Wait 0.5-3s. Mixes chat + health + history + leads. |
| `BurstUser`      | 25% | Power user / script. Wait 0.05-0.5s. Hammers endpoints. |
| `SlowUser`       | 5% | Mobile / flaky network. Wait 5-15s. Longer timeout. |

Total: realistic traffic mix where 70% of requests come from humans, 25% from scripts, 5% from slow clients.

## Endpoints exercised

| Endpoint | Weight | SLO p99 | SLO error rate |
|---|---|---|---|
| `POST /chat` (simple)   | 50 | 2s   | 1% |
| `POST /chat` (tool-call) | 20 | 5s   | 2% |
| `GET /health`           | 15 | 100ms | 0.1% |
| `GET /history/{user}`   | 10 | 1s   | 1% |
| `GET /leads`             | 5  | 1s   | 1% |
| `GET /audit`             | 3  | 2s   | 2% |
| `GET /approvals/pending` | 2  | 1s   | 1% |
| `POST /chat` (burst)    | 80 | 2s   | 1% |
| `POST /chat` (slow)     | 1  | 30s  | 5% |

## What it validates

`on_test_stop` event handler checks each endpoint against its SLO and exits
non-zero if any SLO is violated. CI can then fail the build.

## Recommended test phases

| Phase | Users | Duration | Goal |
|---|---|---|---|
| **Smoke**    | 5   | 1m  | Sanity check after deploy |
| **Load**     | 100 | 10m | Normal traffic |
| **Stress**   | 500 | 15m | Find breaking point |
| **Soak**     | 100 | 24h | Find memory leaks |
| **Spike**    | 0→1000 in 30s | 5m | Test autoscaling |

## Distributed load

For > 1000 users, run Locust in distributed mode:

```bash
# Master
locust -f benchmarks/locustfile.py --master --host=http://localhost:8123

# Worker (one per CPU core)
locust -f benchmarks/locustfile.py --worker --master-host=<master-ip>
```

k6 cloud also supports distributed: `k6 cloud benchmarks/k6-smoke.js`

## CI integration

Add to `.github/workflows/ci.yml` (already wired):

```yaml
benchmark:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: ./scripts/start-stack.sh
    - run: ./benchmarks/run-benchmark.sh http://localhost:8123
    - run: ./scripts/stop-stack.sh
    - uses: actions/upload-artifact@v4
      with:
        name: benchmark-report
        path: benchmarks/reports/
```
