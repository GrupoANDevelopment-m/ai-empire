#!/usr/bin/env bash
#
# run-benchmark.sh — execute a complete load test and produce reports.
#
# Usage:
#   ./benchmarks/run-benchmark.sh http://localhost:8123
#   ./benchmarks/run-benchmark.sh https://staging.your-empire.example.com
#
# Generates:
#   benchmarks/reports/report.html       — full HTML report with charts
#   benchmarks/reports/stats.csv          — per-endpoint stats
#   benchmarks/reports/failures.csv       — failures log
#   benchmarks/reports/slo-report.txt     — SLO compliance summary

set -euo pipefail

HOST="${1:-http://localhost:8123}"
USERS="${USERS:-100}"
SPAWN_RATE="${SPAWN_RATE:-10}"
RUN_TIME="${RUN_TIME:-5m}"
REPORT_DIR="$(cd "$(dirname "$0")" && pwd)/reports"
mkdir -p "$REPORT_DIR"

# Make sure locust is installed
if ! command -v locust >/dev/null 2>&1; then
    echo "Installing locust..."
    python3 -m pip install --break-system-packages --quiet locust 2>&1 | tail -2
fi

# Run
echo "════════════════════════════════════════════════════════════"
echo " AI Empire Load Test"
echo "════════════════════════════════════════════════════════════"
echo " Target:    $HOST"
echo " Users:     $USERS"
echo " Spawn:     $SPAWN_RATE/sec"
echo " Duration:  $RUN_TIME"
echo " Reports:   $REPORT_DIR/"
echo "════════════════════════════════════════════════════════════"

locust -f benchmarks/locustfile.py \
       --host="$HOST" \
       --users="$USERS" \
       --spawn-rate="$SPAWN_RATE" \
       --run-time="$RUN_TIME" \
       --headless \
       --html="$REPORT_DIR/report.html" \
       --csv="$REPORT_DIR/stats" \
       --loglevel INFO

echo
echo "════════════════════════════════════════════════════════════"
echo " Reports:"
echo "   HTML:    $REPORT_DIR/report.html"
echo "   Stats:   $REPORT_DIR/stats_stats.csv"
echo "   Failures:$REPORT_DIR/stats_failures.csv"
echo "════════════════════════════════════════════════════════════"
