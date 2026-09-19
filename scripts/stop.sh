#!/usr/bin/env bash
# AI Empire — Stop tudo
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "🛑 Parando todos os containers AI Empire..."
docker compose down
echo "✓ Tudo parado. Volumes intactos."
