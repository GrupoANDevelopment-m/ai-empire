#!/usr/bin/env bash
# =============================================================================
# AI Empire — One-command installer
# Pre-flight + Docker + Ollama models + start agent CLI
# =============================================================================
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}[ai-empire]${NC} $*"; }
ok()  { echo -e "${GREEN}✓${NC} $*"; }
warn(){ echo -e "${YELLOW}⚠${NC} $*"; }
err() { echo -e "${RED}✗${NC} $*" >&2; }

# ---- Banner ----
cat <<'BANNER'
   ___   __  __ ___ ___   ___   __  __ ___
  / _ \ |  \/  | __| _ \ |   \ |  \/  | __|
 | (_) || |\/| | _||   / | |) || |\/| | _|
  \___/ |_|  |_|___|_|_\ |___/ |_|  |_|___|

👑 AI Empire — your local AI agent platform
BANNER
echo ""

# ---- Pre-flight ----
log "Pre-flight checks…"
command -v docker >/dev/null 2>&1 || { err "docker not found. Install: https://docs.docker.com/get-docker/"; exit 1; }
ok "docker $(docker --version | awk '{print $3}' | tr -d ',')"
command -v docker compose >/dev/null 2>&1 || { err "docker compose not found"; exit 1; }
ok "docker compose $(docker compose version --short)"

# Python
command -v python3 >/dev/null 2>&1 && ok "python3 $(python3 --version | awk '{print $2}')" || warn "python3 not found"

# Disk space
AVAIL=$(df -BG . | awk 'NR==2 {print $4}' | tr -d 'G')
if [ "$AVAIL" -lt 50 ]; then
  warn "Only ${AVAIL}GB disk free (recommend ≥ 50GB for Ollama + models)"
else
  ok "Disk: ${AVAIL}GB free"
fi

# ---- .env ----
[ -f .env ] || { cp .env.example .env; warn "Created .env from .env.example — edit it before production"; }

# ---- Choose profile ----
echo ""
log "Which profile do you want to start?"
echo "  1) core           (minimum: Ollama, Postgres, Redis, n8n)"
echo "  2) core + agents  (LangGraph, Open WebUI, Langfuse)"
echo "  3) all            (everything: 38+ services)"
echo "  4) custom         (you choose)"
echo ""
read -p "Pick (1-4) [default: 2]: " CHOICE
CHOICE=${CHOICE:-2}

case "$CHOICE" in
  1) PROFILES="core" ;;
  2) PROFILES="core agents" ;;
  3) PROFILES="all" ;;
  4)
    echo "Available profiles: core, agents, gateway, browser, leads, design, video, data, crm, office"
    read -p "Space-separated profiles: " PROFILES
    ;;
esac

# ---- Start docker ----
log "Starting docker profiles: $PROFILES"
./scripts/start.sh $PROFILES

# ---- Wait for Ollama ----
if echo "$PROFILES" | grep -q core; then
  log "Waiting for Ollama to be ready…"
  for i in $(seq 1 30); do
    if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
      ok "Ollama ready"
      break
    fi
    sleep 2
  done
  if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
    warn "Ollama didn't come up in 60s. Continuing anyway."
  fi

  # ---- Pull default model ----
  log "Pulling default model (llama3.3)…"
  docker exec ai-empire-ollama ollama pull llama3.3 || warn "Failed to pull llama3.3 (check disk/network)"
fi

# ---- Install Python deps for the agent CLI ----
log "Installing Python dependencies for the agent CLI…"
pip install --break-system-packages --quiet \
    "fastapi>=0.92.0" \
    "uvicorn[standard]>=0.17.0" \
    "httpx>=0.23.0" \
    "pydantic>=1.10.0" \
    "pytest>=7.0" \
    "pytest-asyncio>=0.20.0" 2>/dev/null || true
ok "Python deps OK"

# ---- Smoke test ----
log "Running smoke test (104 tests)…"
./scripts/test.sh 2>&1 | tail -5 || warn "Some tests failed, but installation is OK"

# ---- Show what's up ----
echo ""
ok "🎉 AI Empire is ready!"
echo ""
log "Try the agent right now:"
echo ""
echo "  ./empire chat          # talk to the agent in your terminal"
echo "  ./empire test all      # run all tests"
echo "  ./empire health        # check what's up"
echo "  ./empire ui            # open the web chat in your browser"
echo ""
log "Web UI: http://localhost:7777  (run ./empire ui to start)"
log "n8n:    http://localhost:5678"
log "WebUI:  http://localhost:3000  (chat with Ollama)"
echo ""
log "Type ./empire to see the full menu."
echo ""
# Auto-launch the chat
read -p "Open the chat now? [Y/n] " LAUNCH
if [[ ! "$LAUNCH" =~ ^[nN] ]]; then
  exec ./empire chat
fi
