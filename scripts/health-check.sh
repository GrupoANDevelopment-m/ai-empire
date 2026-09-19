#!/usr/bin/env bash
# AI Empire — Health check
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }

check() {
  local name=$1 url=$2
  if curl -fsS -m 3 "$url" >/dev/null 2>&1; then
    ok "$name → $url"
  else
    fail "$name → $url (não responde)"
  fi
}

check "Ollama"      "http://localhost:11434/api/tags"
check "Open WebUI"   "http://localhost:3000"
check "n8n"          "http://localhost:5678"
check "Flowise"      "http://localhost:3001"
check "Langfuse"     "http://localhost:3002"
check "LangGraph"    "http://localhost:8123/health"
check "Browser-Use"  "http://localhost:8001/health"
check "Penpot"       "http://localhost:9001"
check "ComfyUI"      "http://localhost:8188"
check "SearXNG"      "http://localhost:8888"
check "Qdrant"       "http://localhost:6333"
check "Chatwoot"     "http://localhost:3004"
check "Dittofeed"    "http://localhost:3005"
check "Stirling-PDF" "http://localhost:3014"
check "Whisper"      "http://localhost:9000"
check "Postgres"     "http://localhost:5432" || true
echo ""
docker compose ps
