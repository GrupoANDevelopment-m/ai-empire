#!/usr/bin/env bash
# AI Empire — Update
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "📥 Pulling latest images..."
docker compose pull
echo "🔨 Rebuilding custom services..."
docker compose build
echo "♻️  Restarting..."
docker compose up -d
echo "✓ Update completo. Health: ./scripts/health-check.sh"
