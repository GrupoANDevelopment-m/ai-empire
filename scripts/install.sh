#!/usr/bin/env bash
# =============================================================================
# AI EMPIRE — Bootstrap Installer
# Prepara o ambiente, baixa modelos Ollama, valida tudo
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Cores
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[ai-empire]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*" >&2; }

# ---- Pré-requisitos ----
log "Verificando pré-requisitos..."

command -v docker >/dev/null 2>&1 || { err "docker não instalado. Instale: https://docs.docker.com/get-docker/"; exit 1; }
ok "docker $(docker --version | awk '{print $3}')"

command -v docker compose >/dev/null 2>&1 || { err "docker compose não instalado."; exit 1; }
ok "docker compose $(docker compose version --short)"

if docker compose ls | grep -q "gpu"; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    ok "nvidia-smi detectado (GPU disponível)"
  else
    warn "Docker GPU runtime presente mas nvidia-smi não detectado (CPU only)"
  fi
fi

# Espaço em disco (mínimo 50GB pra Ollama + models + storage)
AVAIL=$(df -BG "$ROOT" | awk 'NR==2 {print $4}' | tr -d 'G')
if [ "$AVAIL" -lt 50 ]; then
  warn "Espaço em disco: ${AVAIL}GB livres (recomendado ≥ 50GB)"
else
  ok "Espaço em disco: ${AVAIL}GB"
fi

# ---- .env ----
if [ ! -f .env ]; then
  log "Criando .env a partir de .env.example..."
  cp .env.example .env
  warn "EDITE .env antes de produção (senhas, API keys, etc.)"
else
  ok ".env já existe"
fi

# ---- Diretórios ----
mkdir -p config/{caddy,postgres,searxng,ollama}
mkdir -p assets/comfyui-workflows
mkdir -p shared/{leads,design,exports,logs}
ok "Diretórios criados"

# ---- Caddyfile default ----
if [ ! -f config/caddy/Caddyfile ]; then
cat > config/caddy/Caddyfile <<'EOF'
# AI Empire — reverse proxy
# Edite para mapear domínios aos serviços internos

(common) {
  encode zstd gzip
  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    X-Content-Type-Options "nosniff"
    X-Frame-Options "SAMEORIGIN"
  }
  reverse_proxy {args[0]} {args[1]}
}

:80 {
  import common http://open-webui:8080
}

:443 {
  import common https://open-webui:8080
}
EOF
  ok "Caddyfile default criado"
fi

# ---- Postgres init ----
cat > config/postgres/init.sql <<'EOF'
-- AI Empire — initial schema
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- Tabela de leads
CREATE TABLE IF NOT EXISTS leads (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  source TEXT,
  name TEXT,
  email TEXT,
  phone TEXT,
  company TEXT,
  role TEXT,
  linkedin_url TEXT,
  website TEXT,
  status TEXT DEFAULT 'new',
  score INT DEFAULT 0,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS leads_status_idx ON leads(status);
CREATE INDEX IF NOT EXISTS leads_score_idx ON leads(score DESC);

-- Tabela de outreach
CREATE TABLE IF NOT EXISTS outreach (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
  channel TEXT NOT NULL,
  status TEXT DEFAULT 'queued',
  message TEXT,
  sent_at TIMESTAMPTZ,
  response_at TIMESTAMPTZ,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS outreach_lead_idx ON outreach(lead_id);
CREATE INDEX IF NOT EXISTS outreach_status_idx ON outreach(status);

-- Tabela de conteúdo (designs, posts, vídeos)
CREATE TABLE IF NOT EXISTS content (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  kind TEXT NOT NULL,
  title TEXT,
  body TEXT,
  media_url TEXT,
  status TEXT DEFAULT 'draft',
  scheduled_for TIMESTAMPTZ,
  published_at TIMESTAMPTZ,
  channels TEXT[],
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS content_status_idx ON content(status);
CREATE INDEX IF NOT EXISTS content_kind_idx ON content(kind);

-- Tabela de execuções do agente
CREATE TABLE IF NOT EXISTS agent_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  agent_name TEXT NOT NULL,
  input JSONB,
  output JSONB,
  state JSONB,
  status TEXT DEFAULT 'running',
  error TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS agent_runs_agent_idx ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS agent_runs_status_idx ON agent_runs(status);
EOF
ok "Postgres init.sql criado"

# ---- Ollama config ----
cat > config/ollama/ollama.env <<'EOF'
OLLAMA_HOST=0.0.0.0:11434
OLLAMA_KEEP_ALIVE=24h
OLLAMA_MAX_LOADED_MODELS=2
EOF
ok "Ollama config criado"

# ---- SearXNG config ----
cat > config/searxng/settings.yml <<'EOF'
use_default_settings: true
server:
  port: 8080
  bind_address: 0.0.0.0
search:
  default_lang: "pt-BR"
  formats:
    - html
    - json
EOF
ok "SearXNG config criado"

# ---- Subir core ----
log "Subindo serviços core (Ollama, Postgres, Redis)..."
docker compose --profile core up -d

# ---- Esperar Ollama ----
log "Aguardando Ollama ficar healthy..."
for i in {1..30}; do
  if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
    ok "Ollama respondendo"
    break
  fi
  sleep 2
done

# ---- Baixar modelos ----
if [ -n "${OLLAMA_MODELS:-}" ]; then
  IFS=',' read -ra MODELS <<< "$OLLAMA_MODELS"
  for model in "${MODELS[@]}"; do
    model=$(echo "$model" | xargs)
    log "Baixando modelo Ollama: $model"
    docker exec ai-empire-ollama ollama pull "$model" || warn "Falha ao baixar $model (pode estar offline)"
  done
fi

ok "Bootstrap completo!"
echo ""
log "Próximos passos:"
echo "  1. Edite .env (senhas, API keys)"
echo "  2. Suba profiles adicionais:  ./scripts/start.sh agents browser leads design"
echo "  3. Acesse:"
echo "     - n8n:        http://localhost:5678"
echo "     - Open WebUI: http://localhost:3000"
echo "     - Langfuse:   http://localhost:3002"
echo "     - Penpot:     http://localhost:9001"
echo "     - ComfyUI:    http://localhost:8188"
echo ""
log "Tudo OK. Bem-vindo ao AI Empire. 👑"
