#!/usr/bin/env bash
#
# run-full.sh — run OWASP ZAP full scan (passive + active attacks).
#
# WARNING: This runs real attacks (XSS, SQLi, CSRF, etc) against the target.
# ONLY run against staging or your own dev environment.
#
# Usage:
#   ./security/zap/run-full.sh https://staging.your-empire.example.com
#

set -euo pipefail

TARGET="${1:-http://localhost:7777}"
REPORT_DIR="$(dirname "$0")/reports"
mkdir -p "$REPORT_DIR"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
REPORT="full-${TIMESTAMP}.html"
JSON_REPORT="full-${TIMESTAMP}.json"

echo "════════════════════════════════════════════════════════════"
echo " ZAP Full Scan (active attacks)"
echo "════════════════════════════════════════════════════════════"
echo " ⚠️  This performs real attacks against the target."
echo " Target:  $TARGET"
echo " Reports: $REPORT_DIR/{$REPORT,$JSON_REPORT}"
echo "════════════════════════════════════════════════════════════"

docker run --rm \
    -v "$REPORT_DIR:/zap/reports:rw" \
    --network host \
    ghcr.io/zaproxy/zaproxy:stable \
    zap-full-scan.py \
        -t "$TARGET" \
        -r "/zap/reports/$REPORT" \
        -J "/zap/reports/$JSON_REPORT" \
        -I \
        -m 10

echo
echo "════════════════════════════════════════════════════════════"
echo " Reports: $REPORT_DIR/{$REPORT,$JSON_REPORT}"
echo "════════════════════════════════════════════════════════════"
