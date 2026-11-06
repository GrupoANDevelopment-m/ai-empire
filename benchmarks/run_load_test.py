"""Real load test — measures this checkout and writes the results.

Runs a concurrency sweep against the running AI Empire API and records the
measured latency percentiles, throughput and error counts. The output is a
real measurement of the machine it ran on; nothing is synthesised.

Usage:
    python3 benchmarks/run_load_test.py --base-url http://127.0.0.1:8099 \
        --out benchmarks/data/production_load_test.json

Requires the API to be running. Authenticated scenarios use the local admin
account unless --email/--password are given.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _request(url: str, headers: dict, method: str = "GET",
             body: bytes | None = None, timeout: float = 30.0):
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        payload = e.read()
        status = e.code
    except Exception as e:
        return time.perf_counter() - t0, 0, str(e)
    return time.perf_counter() - t0, status, payload


def percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"p50_ms": 0, "p95_ms": 0, "p99_ms": 0}
    s = sorted(samples)
    def pct(p: float) -> float:
        if len(s) == 1:
            return round(s[0] * 1000, 3)
        k = (len(s) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(s) - 1)
        return round((s[lo] + (s[hi] - s[lo]) * (k - lo)) * 1000, 3)
    return {"p50_ms": pct(0.50), "p95_ms": pct(0.95), "p99_ms": pct(0.99)}


def run_scenario(name: str, url: str, headers: dict,
                 concurrency: int, total_requests: int) -> dict:
    """Fire `total_requests` requests with `concurrency` workers."""
    latencies: list[float] = []
    errors = 0
    statuses: dict[str, int] = {}
    lock = threading.Lock()
    counter = {"n": 0}

    def worker():
        while True:
            with lock:
                if counter["n"] >= total_requests:
                    return
                counter["n"] += 1
            dt, status, _ = _request(url, headers)
            with lock:
                latencies.append(dt)
                key = str(status) if status else "error"
                statuses[key] = statuses.get(key, 0) + 1
                if not status or status >= 400:
                    errors_local[0] += 1

    errors_local = [0]
    t0 = time.perf_counter()
    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duration = time.perf_counter() - t0

    pct = percentiles(latencies)
    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "duration_seconds": round(duration, 4),
        "requests_per_second": round(total_requests / duration, 2) if duration else 0,
        **pct,
        "errors": errors_local[0],
        "status_codes": statuses,
        "success_rate": round(1 - errors_local[0] / total_requests, 6)
        if total_requests else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8099")
    ap.add_argument("--email", default="admin@empire.local")
    ap.add_argument("--password", default="empire")
    ap.add_argument("--levels", default="1,10,50,100")
    ap.add_argument("--requests", type=int, default=300)
    ap.add_argument("--out", default=str(ROOT / "benchmarks/data/production_load_test.json"))
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    levels = [int(x) for x in args.levels.split(",") if x.strip()]

    # authenticate for the protected scenario
    token = ""
    body = json.dumps({"email": args.email,
                       "password": args.password}).encode()
    dt, status, payload = _request(
        f"{base}/api/auth/login",
        {"Content-Type": "application/json"}, "POST", body)
    if status == 200:
        try:
            token = json.loads(payload).get("access_token", "")
        except Exception:
            token = ""
    if not token:
        print("AVISO: sem token; só o cenário público será medido.",
              file=sys.stderr)

    auth = {"Authorization": f"Bearer {token}"} if token else {}

    scenarios = []
    print(f"medindo {base} …")
    for c in levels:
        n = max(args.requests, c)
        r = run_scenario("GET /health", f"{base}/health", {}, c, n)
        scenarios.append({"name": "GET /health (no auth)",
                          "concurrency_levels": [c], "results": [r]})
        print(f"  /health   c={c:<4} {r['requests_per_second']:>9} rps  "
              f"p50={r['p50_ms']}ms p95={r['p95_ms']}ms err={r['errors']}")

    if auth:
        for c in levels:
            n = max(args.requests, c)
            r = run_scenario("GET /api/capabilities",
                              f"{base}/api/capabilities", auth, c, n)
            scenarios.append({"name": "GET /api/capabilities (JWT)",
                              "concurrency_levels": [c], "results": [r]})
            print(f"  /caps     c={c:<4} {r['requests_per_second']:>9} rps  "
                  f"p50={r['p50_ms']}ms p95={r['p95_ms']}ms err={r['errors']}")

    total_requests = sum(r["total_requests"]
                          for s in scenarios for r in s["results"])
    total_errors = sum(r["errors"]
                        for s in scenarios for r in s["results"])

    out = {
        "test_name": "AI Empire API load test",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "method": "benchmarks/run_load_test.py — urllib workers, one "
                  "process, real HTTP requests against a locally running "
                  "API. Percentiles computed from the measured samples.",
        "honesty_note": (
            "These numbers were measured on the machine described in "
            "'environment' below, on a single API process. They are NOT "
            "measurements of a managed production deployment. Re-run the "
            "script against your own environment to get numbers that "
            "describe it."),
        "duration_seconds": round(
            sum(r["duration_seconds"] for s in scenarios for r in s["results"]), 3),
        "environment": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "api_processes": 1,
            "note": "single local uvicorn process; no Kubernetes, no managed "
                    "database, no load balancer in this run",
        },
        "totals": {
            "scenarios": len(scenarios),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "success_rate": round(1 - total_errors / total_requests, 6)
            if total_requests else 0,
        },
        "scenarios": scenarios,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nescrito: {out_path}")

    csv_path = out_path.with_suffix(".csv")
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "concurrency", "total_requests", "duration_s",
                    "rps", "p50_ms", "p95_ms", "p99_ms", "errors",
                    "success_rate", "status_codes"])
        for sc in scenarios:
            for r in sc["results"]:
                w.writerow([sc["name"], r["concurrency"], r["total_requests"],
                            r["duration_seconds"], r["requests_per_second"],
                            r["p50_ms"], r["p95_ms"], r["p99_ms"], r["errors"],
                            r["success_rate"],
                            ";".join(f"{k}:{v}" for k, v in r["status_codes"].items())])
    print(f"escrito: {csv_path}")
    print(f"total: {total_requests} requisições, {total_errors} erros")
    return 0


if __name__ == "__main__":
    sys.exit(main())
