#!/usr/bin/env bash
#
# run-all.sh — run all 3 ZAP scans (baseline, full, API) and produce a summary.
#
# Usage:
#   ./security/zap/run-all.sh https://staging.your-empire.example.com
#

set -euo pipefail

TARGET="${1:-http://localhost:7777}"
API_TARGET="${2:-http://localhost:8123}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Running baseline scan..."
"$SCRIPT_DIR/run-baseline.sh" "$TARGET" || true
echo

echo "Running full scan..."
"$SCRIPT_DIR/run-full.sh" "$TARGET" || true
echo

echo "Running API scan..."
"$SCRIPT_DIR/run-api.sh" "$API_TARGET" || true
echo

echo "════════════════════════════════════════════════════════════"
echo " Summary of latest reports"
echo "════════════════════════════════════════════════════════════"
ls -lat "$SCRIPT_DIR/reports/" | head -20
echo

LATEST_JSON=$(ls -t "$SCRIPT_DIR/reports/"*.json 2>/dev/null | head -1)
if [ -n "$LATEST_JSON" ]; then
    echo "Latest scan summary:"
    python3 -c "
import json, sys
try:
    with open('$LATEST_JSON') as f:
        d = json.load(f)
    s = d.get('site', [{}])[0].get('counts', {})
    high, med, low, info = s.get('high', 0), s.get('medium', 0), s.get('low', 0), s.get('info', 0)
    print(f'  High: {high}, Medium: {med}, Low: {low}, Info: {info}')
    if high > 0:
        print('  ⚠️  HIGH risk findings — review before deploying to production!')
        sys.exit(2)
except Exception as e:
    print(f'  (parse error: {e})')
"
fi
