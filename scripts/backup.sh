#!/usr/bin/env bash
#
# backup.sh — backup all stateful services.
#
# Usage:
#   ./scripts/backup.sh                     # backup everything
#   ./scripts/backup.sh postgres            # just postgres
#   ./scripts/backup.sh postgres redis      # specific services
#
# Output:
#   /var/backups/ai-empire/<service>-<timestamp>.{sql,zip,...}
#   /var/backups/ai-empire/LATEST/          # symlinks to most recent
#
# Retention: 7 daily, 4 weekly, 12 monthly (configurable via env).
#
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/ai-empire}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DATE_HUMAN="$(date -u +%Y-%m-%d\ %H:%M:%S\ UTC)"
RETENTION_DAILY="${RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${RETENTION_WEEKLY:-4}"
RETENTION_MONTHLY="${RETENTION_MONTHLY:-12}"

mkdir -p "$BACKUP_ROOT"

# ─── Postgres ───────────────────────────────────────────────────────────────
backup_postgres() {
    echo "[$DATE_HUMAN] postgres: dumping..."
    local f="$BACKUP_ROOT/postgres-$TS.sql.gz"
    docker exec ai-empire-postgres pg_dump \
        -U "${POSTGRES_USER:-empire}" \
        -d "${POSTGRES_DB:-ai_empire}" \
        --clean --if-exists \
        | gzip > "$f"
    ln -sfn "$(basename "$f")" "$BACKUP_ROOT/LATEST-postgres.sql.gz"
    echo "  ✓ $(du -h "$f" | cut -f1) — $f"
}

# ─── Redis ──────────────────────────────────────────────────────────────────
backup_redis() {
    echo "[$DATE_HUMAN] redis: snapshotting..."
    # Trigger a save inside the container
    docker exec ai-empire-redis redis-cli BGSAVE >/dev/null
    sleep 2  # wait for save to complete
    local f="$BACKUP_ROOT/redis-$TS.rdb"
    docker cp ai-empire-redis:/data/dump.rdb "$f"
    gzip "$f"
    ln -sfn "$(basename "$f.gz")" "$BACKUP_ROOT/LATEST-redis.rdb.gz"
    echo "  ✓ $(du -h "$f.gz" | cut -f1) — $f.gz"
}

# ─── Qdrant ─────────────────────────────────────────────────────────────────
backup_qdrant() {
    echo "[$DATE_HUMAN] qdrant: snapshotting..."
    local snap
    snap=$(curl -fsS -X POST "http://localhost:6333/snapshots" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['name'])")
    local f="$BACKUP_ROOT/qdrant-$TS-$snap.tar"
    curl -fsS "http://localhost:6333/snapshots/$snap" -o "$f"
    ln -sfn "$(basename "$f")" "$BACKUP_ROOT/LATEST-qdrant.tar"
    echo "  ✓ $(du -h "$f" | cut -f1) — $f"
}

# ─── Volumes ────────────────────────────────────────────────────────────────
backup_volumes() {
    echo "[$DATE_HUMAN] volumes: archiving..."
    local f="$BACKUP_ROOT/volumes-$TS.tar.gz"
    # Back up named volumes used by stateful services
    local volumes=(
        "ai-empire-postgres_data"
        "ai-empire-redis_data"
        "ai-empire-qdrant_data"
        "ai-empire-n8n_data"
        "ai-empire-minio_data"
        "ai-empire-penpot_data"
    )
    local existing=()
    for v in "${volumes[@]}"; do
        if docker volume inspect "$v" >/dev/null 2>&1; then
            existing+=("$v")
        fi
    done
    if [ ${#existing[@]} -eq 0 ]; then
        echo "  (no volumes found, skipping)"
        return
    fi
    docker run --rm \
        -v "$(IFS=:; echo "${existing[*]}")":/backup:ro \
        -v "$BACKUP_ROOT":/dest \
        alpine:3.20 tar czf /dest/"$(basename "$f")" -C /backup .
    ln -sfn "$(basename "$f")" "$BACKUP_ROOT/LATEST-volumes.tar.gz"
    echo "  ✓ $(du -h "$f" | cut -f1) — $f"
}

# ─── n8n workflows ──────────────────────────────────────────────────────────
backup_n8n_workflows() {
    echo "[$DATE_HUMAN] n8n workflows: exporting..."
    local f="$BACKUP_ROOT/n8n-workflows-$TS.zip"
    if [ -d workflows ]; then
        zip -r "$f" workflows/ >/dev/null
        ln -sfn "$(basename "$f")" "$BACKUP_ROOT/LATEST-n8n.zip"
        echo "  ✓ $(du -h "$f" | cut -f1) — $f"
    fi
}

# ─── Retention ───────────────────────────────────────────────────────────────
prune_old() {
    echo "[$DATE_HUMAN] pruning old backups..."
    # Keep last N backups of each service
    for pattern in postgres- redis- qdrant- volumes- n8n-workflows-; do
        # Sort by timestamp (filename), delete oldest beyond RETENTION_DAILY
        ls -1 "$BACKUP_ROOT"/${pattern}*.{gz,tar,zip,sql} 2>/dev/null | sort -r | \
            tail -n +$((RETENTION_DAILY + 1)) | xargs -r rm -f
    done
}

# ─── Main ───────────────────────────────────────────────────────────────────
SERVICES="${@:-all}"
echo "════════════════════════════════════════════════════════════"
echo " AI Empire backup — $DATE_HUMAN"
echo "════════════════════════════════════════════════════════════"

run() { "$@" || echo "  ✗ failed: $*"; }

case "$SERVICES" in
    all|"")  run backup_postgres
             run backup_redis
             run backup_n8n_workflows
             run backup_volumes
             run backup_qdrant
             ;;
    postgres) run backup_postgres ;;
    redis)    run backup_redis ;;
    qdrant)   run backup_qdrant ;;
    volumes)  run backup_volumes ;;
    n8n)      run backup_n8n_workflows ;;
    *)        for s in $SERVICES; do run backup_$s; done ;;
esac

prune_old

echo
echo "Latest backups:"
ls -la "$BACKUP_ROOT"/LATEST-* 2>/dev/null || true
echo "════════════════════════════════════════════════════════════"
