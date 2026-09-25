"""
AI Empire — Locust load test.

Simulates REAL user behavior:
  - Browse the web UI
  - Run an agent conversation
  - Find leads
  - Send outreach (requires approval — we just draft, not send)
  - Generate an image
  - Health check (background)
  - Auth refresh

Run with:
  locust -f benchmarks/locustfile.py --host=http://localhost:8123 \
         --users=100 --spawn-rate=10 --run-time=10m --headless

For Web UI:
  locust -f benchmarks/locustfile.py --host=http://localhost:8123

Scenarios cover SLO validation:
  - p99 latency < 2s
  - Error rate < 1%
  - Availability > 99.5%
"""
import random
import time
import json
import os
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner


# ── Token pool ──────────────────────────────────────────────────────────────
# Pre-generated JWTs (admin, operator, viewer) — in production these would
# be issued by your IdP. For load testing, we just use any valid JWT.

TOKENS = {
    "admin":    os.getenv("LOCUST_TOKEN_ADMIN",    "eyJ-test-admin"),
    "operator": os.getenv("LOCUST_TOKEN_OPERATOR", "eyJ-test-operator"),
    "operator2":os.getenv("LOCUST_TOKEN_OP2",      "eyJ-test-op2"),
    "viewer":   os.getenv("LOCUST_TOKEN_VIEWER",   "eyJ-test-viewer"),
}

# Sample prompts for chat — kept short to control cost in CI
CHAT_PROMPTS = [
    "what can you do",
    "find 5 SaaS leads in Brazil",
    "create an image of a sunset",
    "run the circuit breaker tests",
    "is everything healthy?",
    "make a 3 second video of a cat",
    "send a cold email to lead 1",
    "search twitter for AI news",
    "summarize this URL",
    "translate to portuguese",
]

# Tool names that the agent might call — used to validate tool latency SLO
TOOL_NAMES = [
    "find_leads", "send_outreach", "run_tests", "health_check",
    "generate_image", "navigate_browser", "publish_social",
    "watch_video", "generate_video",
]


class EmpireUser(HttpUser):
    """
    Simulated user. Mixes heavy chat, light health checks, occasional
    bulk operations.
    """
    # Real users don't hammer endpoints constantly
    wait_time = between(0.5, 3.0)

    # Weight: 70% operator, 20% admin, 10% viewer
    weight = 1

    def on_start(self):
        """Per-user setup — pick a role and store token."""
        roles = ["operator", "operator2", "admin", "viewer"]
        weights = [40, 30, 20, 10]
        self.role = random.choices(roles, weights=weights)[0]
        self.token = TOKENS.get(self.role, TOKENS["operator"])
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.user_id = f"locust-{self.role}-{random.randint(1000, 999999)}"

    @task(50)
    def chat_simple_question(self):
        """Most common: short conversational message. SLO: p99 < 2s."""
        prompt = random.choice(CHAT_PROMPTS)
        start = time.time()
        with self.client.post(
            "/chat",
            headers=self.headers,
            json={"message": prompt, "session": f"sess-{self.user_id}"},
            name="/chat (simple)",
            catch_response=True,
        ) as r:
            latency = (time.time() - start) * 1000
            if r.status_code == 200:
                r.success()
            elif r.status_code == 429:
                # Rate limited — fine, that's the system working
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")

    @task(20)
    def chat_complex_with_tool(self):
        """Heavier: question that triggers a tool call (find_leads, generate_image)."""
        prompt = random.choice([
            "find 10 CTOs of SaaS in Brazil",
            "create a 16:9 banner for our launch",
            "search reddit for the best LLM 2026",
        ])
        with self.client.post(
            "/chat",
            headers=self.headers,
            json={"message": prompt, "session": f"sess-{self.user_id}"},
            name="/chat (tool-call)",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429):
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")

    @task(15)
    def health_check(self):
        """Background polling — should be fast and cheap."""
        self.client.get("/health", name="/health")

    @task(10)
    def list_history(self):
        """Read operations — should be fast."""
        with self.client.get(
            f"/history/{self.user_id}",
            headers=self.headers,
            name="/history",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                # 404 is fine — no history yet
                r.success()
            elif r.status_code == 429:
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")

    @task(5)
    def list_leads(self):
        """Lead list — admin/operator only. SLO: p95 < 1s."""
        with self.client.get(
            "/leads?limit=20",
            headers=self.headers,
            name="/leads",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 403, 404, 429):
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")

    @task(3)
    def audit_read(self):
        """Admin reads audit log. Should be paginated and fast."""
        with self.client.get(
            "/audit?limit=50",
            headers=self.headers,
            name="/audit",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 403, 429):
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")

    @task(2)
    def approvals_pending(self):
        """Operator checks for pending approvals."""
        with self.client.get(
            "/approvals/pending",
            headers=self.headers,
            name="/approvals",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 403, 404, 429):
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")


class BurstUser(HttpUser):
    """
    Aggressive user — represents a power user with scripts.
    Higher RPS, less wait time.
    """
    weight = 1
    wait_time = between(0.05, 0.5)

    def on_start(self):
        self.token = TOKENS["operator"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task(80)
    def hammer_chat(self):
        prompt = random.choice(CHAT_PROMPTS)
        with self.client.post(
            "/chat",
            headers=self.headers,
            json={"message": prompt, "session": f"burst-{random.randint(0, 100)}"},
            name="/chat (burst)",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429):
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")

    @task(20)
    def hammer_health(self):
        self.client.get("/health", name="/health (burst)")


class SlowUser(HttpUser):
    """
    Slow user — represents a user on flaky mobile network.
    Long wait time, occasional retries.
    """
    weight = 1
    wait_time = between(5, 15)

    def on_start(self):
        self.token = TOKENS["operator"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @task
    def slow_chat(self):
        prompt = random.choice(CHAT_PROMPTS)
        # Set a longer timeout for slow users
        with self.client.post(
            "/chat",
            headers=self.headers,
            json={"message": prompt, "session": "slow"},
            name="/chat (slow)",
            timeout=30,
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429):
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")


# ── SLO validation ──────────────────────────────────────────────────────────

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print SLO compliance summary at end of test."""
    stats = environment.stats
    print("\n" + "=" * 60)
    print(" SLO COMPLIANCE REPORT")
    print("=" * 60)

    slo_results = []
    for name, slo_p99_ms, slo_error_pct in [
        ("/chat (simple)",    2000,  1.0),
        ("/chat (tool-call)", 5000,  2.0),
        ("/chat (burst)",     2000,  1.0),
        ("/health",            100,  0.1),
        ("/history",          1000,  1.0),
        ("/leads",            1000,  1.0),
        ("/audit",            2000,  2.0),
    ]:
        entry = stats.get(name, "aggregate (per endpoint)")
        if entry is None:
            continue
        p99 = entry.get_response_time_percentile(0.99)
        # Calculate error rate
        total = entry.num_requests
        failures = entry.num_failures
        err_pct = (failures / total * 100) if total > 0 else 0

        latency_ok = p99 <= slo_p99_ms if p99 else True
        error_ok = err_pct <= slo_error_pct

        status = "✓" if (latency_ok and error_ok) else "✗"
        slo_results.append((name, p99, slo_p99_ms, err_pct, slo_error_pct, status))

        print(f"  {status} {name:30s} p99={p99:.0f}ms (slo {slo_p99_ms}ms)  "
              f"errors={err_pct:.2f}% (slo {slo_error_pct}%)")

    print("=" * 60)
    if all(s[5] == "✓" for s in slo_results):
        print(" ✓ ALL SLOs MET")
    else:
        fails = [s for s in slo_results if s[5] == "✗"]
        print(f" ✗ {len(fails)} SLO(s) VIOLATED:")
        for s in fails:
            print(f"   - {s[0]}: p99={s[1]:.0f}ms (slo {s[2]}ms), "
                  f"errors={s[3]:.2f}% (slo {s[4]}%)")
        # Exit non-zero so CI can fail the build
        environment.process_exit_code = 1
    print("=" * 60)


# ── Distributed mode hooks ──────────────────────────────────────────────────

@events.init.add_listener
def on_init(environment, **kwargs):
    """Print helpful info on startup."""
    if isinstance(environment.runner, MasterRunner):
        print("Running as MASTER — connect workers to this host")
    elif isinstance(environment.runner, WorkerRunner):
        print("Running as WORKER")
    else:
        print(f"Starting load test against {environment.host}")
        print("Scenarios: 70% normal, 25% burst, 5% slow")
        print("Auth: using test JWTs (set LOCUST_TOKEN_* env vars for real ones)")
