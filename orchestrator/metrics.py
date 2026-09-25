"""
Custom Prometheus metrics for the Empire agent.

Exposes a Counter/Histogram/Gauge per metric family. Wire up at app startup:

  from orchestrator.metrics import metrics
  metrics.start_http_server(port=9091)

Then OTEL collector scrapes these via a sidecar, OR Prometheus scrapes directly.

Metric families:
  empire_http_requests_total{status, method, endpoint}     Counter
  empire_tool_duration_ms{tool, ok}                          Histogram
  empire_llm_cost_usd_total{tenant, model, provider}        Counter
  empire_llm_prompt_tokens_total{tenant, model, provider}   Counter
  empire_llm_completion_tokens_total{...}                   Counter
  empire_llm_total_tokens_total{...}                        Counter
  empire_llm_latency_ms{tenant, model, provider}            Histogram
  empire_sessions_active{tenant}                             Gauge
  empire_hitl_pending{action, tenant}                        Gauge
  empire_hitl_decision_seconds{action}                       Histogram
  empire_hitl_outcomes_total{action, outcome}                Counter
  empire_pii_redactions_total{pattern, action}               Counter
  empire_tenant_violations_total{actor, target_tenant}       Counter
  empire_auth_failures_total{reason}                         Counter
  empire_audit_actions_total{tenant, actor, action}          Counter
"""
import threading
import time
from collections import defaultdict
from typing import Optional

# Lightweight in-process registry — production should use prometheus_client lib.
# We implement a tiny Prometheus exposition format manually to avoid the dep.


class _Counter:
    def __init__(self, name: str, help: str, labels: tuple[str, ...] = ()):
        self.name = name
        self.help = help
        self.labels = labels
        self.values: dict[tuple, float] = defaultdict(float)

    def inc(self, amount: float = 1.0, **labels):
        key = tuple(labels.get(l, "") for l in self.labels)
        self.values[key] += amount

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for labels_tuple, value in sorted(self.values.items()):
            if not labels_tuple:
                lines.append(f"{self.name} {value}")
            else:
                label_str = ",".join(
                    f'{l}="{v}"' for l, v in zip(self.labels, labels_tuple)
                )
                lines.append(f"{self.name}{{{label_str}}} {value}")
        return "\n".join(lines) + "\n"


class _Gauge:
    def __init__(self, name: str, help: str, labels: tuple[str, ...] = ()):
        self.name = name
        self.help = help
        self.labels = labels
        self.values: dict[tuple, float] = {}

    def set(self, value: float, **labels):
        key = tuple(labels.get(l, "") for l in self.labels)
        self.values[key] = value

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} gauge"]
        for labels_tuple, value in sorted(self.values.items()):
            if not labels_tuple:
                lines.append(f"{self.name} {value}")
            else:
                label_str = ",".join(
                    f'{l}="{v}"' for l, v in zip(self.labels, labels_tuple)
                )
                lines.append(f"{self.name}{{{label_str}}} {value}")
        return "\n".join(lines) + "\n"


class _Histogram:
    """Bucketed histogram with predefined buckets."""
    DEFAULT_BUCKETS = (10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000)

    def __init__(self, name: str, help: str, labels: tuple[str, ...] = (),
                 buckets: tuple[float, ...] = DEFAULT_BUCKETS):
        self.name = name
        self.help = help
        self.labels = labels
        self.buckets = buckets
        # counts[key] = {bucket: count}
        self.counts: dict[tuple, dict[float, int]] = defaultdict(
            lambda: {b: 0 for b in buckets}
        )
        self.sums: dict[tuple, float] = defaultdict(float)

    def observe(self, value: float, **labels):
        key = tuple(labels.get(l, "") for l in self.labels)
        self.sums[key] += value
        for b in self.buckets:
            if value <= b:
                self.counts[key][b] += 1

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for key in sorted(self.counts.keys()):
            label_str = (
                ",".join(f'{l}="{v}"' for l, v in zip(self.labels, key))
                if key else ""
            )
            cumulative = 0
            for b in self.buckets:
                cumulative = self.counts[key][b]
                le_label = f',le="{b}"' if label_str else f'le="{b}"'
                full_label = label_str + le_label if label_str else le_label.lstrip(",")
                lines.append(f"{self.name}_bucket{{{full_label}}} {cumulative}")
            inf_label = label_str + ',le="+Inf"' if label_str else 'le="+Inf"'
            lines.append(
                f"{self.name}_bucket{{{inf_label}}} {self.counts[key][self.buckets[-1]]}"
            )
            lines.append(f"{self.name}_sum{{{label_str}}} {self.sums[key]:.3f}")
            lines.append(f"{self.name}_count{{{label_str}}} {sum(self.counts[key].values())}")
        return "\n".join(lines) + "\n"


# ── Metric registry ──────────────────────────────────────────────────────────
class Metrics:
    def __init__(self):
        self.http_requests = _Counter(
            "empire_http_requests_total",
            "Total HTTP requests handled by Empire services",
            ("status", "method", "endpoint"),
        )
        self.tool_duration = _Histogram(
            "empire_tool_duration_ms",
            "Tool execution time in milliseconds",
            ("tool", "ok"),
            buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 15000, 60000, 300000),
        )
        self.llm_cost = _Counter(
            "empire_llm_cost_usd_total",
            "Total LLM cost in USD",
            ("tenant", "model", "provider"),
        )
        self.llm_prompt_tokens = _Counter(
            "empire_llm_prompt_tokens_total",
            "Total prompt tokens sent to LLM",
            ("tenant", "model", "provider"),
        )
        self.llm_completion_tokens = _Counter(
            "empire_llm_completion_tokens_total",
            "Total completion tokens received from LLM",
            ("tenant", "model", "provider"),
        )
        self.llm_total_tokens = _Counter(
            "empire_llm_total_tokens_total",
            "Total tokens (prompt + completion)",
            ("tenant", "model", "provider"),
        )
        self.llm_latency = _Histogram(
            "empire_llm_latency_ms",
            "LLM round-trip latency",
            ("tenant", "model", "provider"),
        )
        self.sessions_active = _Gauge(
            "empire_sessions_active",
            "Currently active sessions",
            ("tenant",),
        )
        self.hitl_pending = _Gauge(
            "empire_hitl_pending",
            "Pending HITL approval requests",
            ("action", "tenant"),
        )
        self.hitl_decision = _Histogram(
            "empire_hitl_decision_seconds",
            "Time from approval creation to decision",
            ("action",),
            buckets=(60, 300, 600, 1800, 3600, 14400, 86400),
        )
        self.hitl_outcomes = _Counter(
            "empire_hitl_outcomes_total",
            "HITL approval outcomes",
            ("action", "outcome"),
        )
        self.pii_redactions = _Counter(
            "empire_pii_redactions_total",
            "PII patterns redacted before logging",
            ("pattern", "action"),
        )
        self.tenant_violations = _Counter(
            "empire_tenant_violations_total",
            "Cross-tenant access attempts",
            ("actor", "target_tenant"),
        )
        self.auth_failures = _Counter(
            "empire_auth_failures_total",
            "Authentication failures",
            ("reason",),
        )
        self.audit_actions = _Counter(
            "empire_audit_actions_total",
            "Audit-logged actions",
            ("tenant", "actor", "action"),
        )
        self._server = None

    def render(self) -> str:
        """Render all metrics in Prometheus exposition format."""
        parts = [
            self.http_requests.render(),
            self.tool_duration.render(),
            self.llm_cost.render(),
            self.llm_prompt_tokens.render(),
            self.llm_completion_tokens.render(),
            self.llm_total_tokens.render(),
            self.llm_latency.render(),
            self.sessions_active.render(),
            self.hitl_pending.render(),
            self.hitl_decision.render(),
            self.hitl_outcomes.render(),
            self.pii_redactions.render(),
            self.tenant_violations.render(),
            self.auth_failures.render(),
            self.audit_actions.render(),
        ]
        return "\n".join(parts)

    def start_http_server(self, port: int = 9091):
        """Start a tiny HTTP server exposing /metrics."""
        from http.server import BaseHTTPRequestHandler, HTTPServer
        m = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a, **k):
                pass
            def do_GET(self):
                if self.path == "/metrics":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.end_headers()
                    self.wfile.write(m.render().encode())
                elif self.path == "/health":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")
                else:
                    self.send_response(404)
                    self.end_headers()

        self._server = HTTPServer(("0.0.0.0", port), H)
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        return thread


metrics = Metrics()
