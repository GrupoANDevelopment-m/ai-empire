#!/bin/bash
# AI Empire — EC2 user data script
# Runs on instance launch. Installs Docker, clones repo, starts services.

set -euo pipefail
exec > >(tee -a /var/log/empire-bootstrap.log)
exec 2>&1

echo "=== AI Empire bootstrap starting at $(date) ==="

# ─── Install Docker ───────────────────────────────────────────────
apt-get update -y
apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  awscli

mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu jammy stable" | tee /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker

# ─── Pull AI Empire ───────────────────────────────────────────────
mkdir -p /opt/ai-empire
cd /opt/ai-empire

# In real deployment, use git+SSH
git clone https://github.com/GrupoANDevelopment-m/ai-empire.git .

# ─── Configure ───────────────────────────────────────────────────
cp .env.example .env
# Random secrets
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(openssl rand -hex 32)|" .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env
sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$(openssl rand -hex 16)|" .env

# ─── Start ────────────────────────────────────────────────────────
./install.sh --non-interactive

# ─── Health check loop ───────────────────────────────────────────
echo "Waiting for services to come up..."
for i in {1..30}; do
  if curl -fs http://localhost:8123/health > /dev/null 2>&1; then
    echo "✓ AI Empire healthy after ${i} attempts"
    break
  fi
  sleep 10
done

# ─── Auto-update cron ───────────────────────────────────────────
(crontab -l 2>/dev/null; echo "0 4 * * * cd /opt/ai-empire && ./scripts/auto_update.py apply >> logs/updates/cron.log 2>&1") | crontab -

# ─── Daily backup to S3 ─────────────────────────────────────────
(crontab -l 2>/dev/null; echo "0 5 * * * /opt/ai-empire/scripts/backup.sh s3") | crontab -

echo "=== AI Empire bootstrap complete at $(date) ==="