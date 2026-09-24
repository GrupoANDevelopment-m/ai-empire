#!/usr/bin/env bash
#
# restore.sh — restore from a backup.
#
# Usage:
#   ./scripts/restore.sh postgres /var/backups/ai-empire/postgres-20260101T000000Z.sql.gz
#   ./scripts/restore.sh redis    /var/backups/ai-empire/redis-20260101T000000Z.rdb.gz
#   ./scripts/restore.sh volumes  /var/backups/ai-empire/volumes-20260101T000000Z.tar.gz
#
# ⚠️  This is DESTRUCTIVE. Always confirm before running.
#
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <postgres|redis|volumes|qdrant> <backup-file>"
    exit 1
fi
SERVICE="$1"; shift
BACKUP="$1"; shift

if [ ! -f "$BACKUP" ]; then
    echo "Backup file not found: $BACKUP"
    exit 1
fi

echo "⚠️  About to restore $SERVICE from $BACKUP"
echo "    This will OVERWRITE the current data."
read -p "Type 'RESTORE' to confirm: " CONFIRM
[ "$CONFIRM" = "RESTORE" ] || { echo "Aborted."; exit 1; }

case "$SERVICE" in
    postgres)
        echo "Stopping services that depend on postgres..."
        docker compose --profile core --profile agents --profile crm stop postgres 2>/dev/null || true
        gunzip -c "$BACKUP" | docker exec -i ai-empire-postgres psql \
            -U "${POSTGRES_USER:-empire}" -d "${POSTGRES_DB:-ai_empire}"
        echo "✓ Postgres restored"
        ;;
    redis)
        echo "Stopping redis..."
        docker compose --profile core stop redis 2>/dev/null || true
        gunzip -c "$BACKUP" > /tmp/dump.rdb
        docker cp /tmp/dump.rdb ai-empire-redis:/data/dump.rdb
        docker compose --profile core start redis 2>/dev/null || true
        echo "✓ Redis restored"
        ;;
    volumes)
        echo "Stopping all services..."
        docker compose --profile core --profile agents stop 2>/dev/null || true
        docker run --rm \
            -v "$(basename "$BACKUP" .tar.gz)_extract":/restore \
            -v "$BACKUP":/backup.tar.gz:ro \
            alpine:3.20 sh -c "tar xzf /backup.tar.gz -C /restore"
        echo "Extracted. Now copy volumes manually:"
        echo "  docker run --rm -v ai-empire-postgres_data:/data -v $(basename $BACKUP .tar.gz)_extract:/backup alpine cp -a /backup/postgres_data/. /data/"
        ;;
    qdrant)
        curl -fsS "http://localhost:6333/snapshots/upload?priority=snapshot" \
            -F "snapshot=@$BACKUP"
        echo "✓ Qdrant snapshot uploaded"
        ;;
    *)
        echo "Unknown service: $SERVICE"
        exit 1
        ;;
esac
