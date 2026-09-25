#!/usr/bin/env bash
#
# run-baseline.sh — run OWASP ZAP baseline scan against a target.
#
# Baseline = passive scan only (no active attacks). Safe to run against
# production. Runs in ~5-10 minutes.
#
# Usage:
#   ./security/zap/run-baseline.sh https://your-empire.example.com
#   ./security/zap/run-baseline.sh http://localhost:7777
#

set -euo pipefail

TARGET="${1:-http://localhost:7777}"
REPORT_DIR="$(dirname "$0")/reports"
mkdir -p "$REPORT_DIR"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
REPORT="baseline-${TIMESTAMP}.html"
JSON_REPORT="baseline-${TIMESTAMP}.json"

echo "════════════════════════════════════════════════════════════"
echo " ZAP Baseline Scan"
echo "════════════════════════════════════════════════════════════"
echo " Target:  $TARGET"
echo " Reports: $REPORT_DIR/{$REPORT,$JSON_REPORT}"
echo "════════════════════════════════════════════════════════════"

# Use Docker (recommended) — image: zaproxy/zap-stable
docker run --rm \
    -v "$REPORT_DIR:/zap/reports:rw" \
    --network host \
    ghcr.io/zaproxy/zaproxy:stable \
    zap-baseline.py \
        -t "$TARGET" \
        -r "/zap/reports/$REPORT" \
        -J "/zap/reports/$JSON_REPORT" \
        -I \
        -m 5  # max minutes to wait for spider

echo
echo "════════════════════════════════════════════════════════════"
echo " Reports written:"
echo "   HTML: $REPORT_DIR/$REPORT"
echo "   JSON: $REPORT_DIR/$JSON_REPORT"
echo
echo " Risk summary:"
python3 -c "
import json
try:
    with open('$REPORT_DIR/$JSON_REPORT') as f:
        d = json.load(f)
    s = d.get('site', [{}])[0].get('counts', {})
    print(f'   High:   {s.get(\"high\", 0)}')
    print(f'   Medium: {s.get(\"medium\", 0)}')
    print(f'   Low:    {s.get(\"low\", 0)}')
    print(f'   Info:   {s.get(\"info\", 0)}')
    high = s.get('high', 0)
    if high > 0:
        print('\\n  ⚠️  HIGH risk findings — review immediately!')
        exit(2)
except Exception as e:
    print(f'  (could not parse summary: {e})')
"
echo "════════════════════════════════════════════════════════════"
