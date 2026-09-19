#!/usr/bin/env bash
# AI Empire — Start profiles
# Uso: ./scripts/start.sh [core] [agents] [browser] [leads] [design] [video] [data] [crm] [office] [all]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROFILES="${*:-core}"
if [ "$*" = "all" ]; then
  PROFILES="core agents browser leads design video data crm office"
fi

echo "🚀 Subindo profiles: $PROFILES"
docker compose $(printf -- '--profile %s ' $PROFILES) up -d
echo "✓ Pronto. Health check: ./scripts/health-check.sh"
