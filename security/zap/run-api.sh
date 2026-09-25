#!/usr/bin/env bash
#
# run-api.sh — run OWASP ZAP API scan against an OpenAPI spec.
#
# Usage:
#   ./security/zap/run-api.sh http://localhost:8123
#   ./security/zap/run-api.sh https://api.your-empire.example.com
#
# Requires ./security/zap/openapi.json to exist (export from FastAPI:
#   curl http://localhost:8123/openapi.json > security/zap/openapi.json
#

set -euo pipefail

TARGET="${1:-http://localhost:8123}"
REPORT_DIR="$(dirname "$0")/reports"
SCRIPT_DIR="$(dirname "$0")"
mkdir -p "$REPORT_DIR"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
REPORT="api-${TIMESTAMP}.html"
JSON_REPORT="api-${TIMESTAMP}.json"

if [ ! -f "$SCRIPT_DIR/openapi.json" ]; then
    echo "Downloading OpenAPI spec from $TARGET/openapi.json..."
    curl -fsS "$TARGET/openapi.json" -o "$SCRIPT_DIR/openapi.json"
    echo "✓ Saved to $SCRIPT_DIR/openapi.json"
fi

echo "════════════════════════════════════════════════════════════"
echo " ZAP API Scan"
echo "════════════════════════════════════════════════════════════"
echo " Target: $TARGET"
echo " Spec:   $SCRIPT_DIR/openapi.json"
echo "════════════════════════════════════════════════════════════"

docker run --rm \
    -v "$REPORT_DIR:/zap/reports:rw" \
    -v "$SCRIPT_DIR/openapi.json:/zap/openapi.json:ro" \
    --network host \
    ghcr.io/zaproxy/zaproxy:stable \
    zap-api-scan.py \
        -t "$TARGET" \
        -f openapi \
        -O "/zap/openapi.json" \
        -r "/zap/reports/$REPORT" \
        -J "/zap/reports/$JSON_REPORT" \
        -I

echo "Reports: $REPORT_DIR/{$REPORT,$JSON_REPORT}"
