#!/usr/bin/env bash
# AI Empire — Logs agregados
# Uso: ./scripts/logs.sh [serviço]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose logs -f --tail=100 "$@"
