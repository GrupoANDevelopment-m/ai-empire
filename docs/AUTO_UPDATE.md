# Auto-Update System

AI Empire updates itself safely — checks for image updates, backs up before applying, rolls back on failure.

## How it works

```
┌────────────────────────────────────────────────────────────────────┐
│                          TRIGGER                                   │
│   • Cron (4 AM daily)        • Manual API call      • Watchtower   │
│   `scripts/auto_update.py apply`   POST /api/system/update/apply   │
└─────────────────┬──────────────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────────────────────────────────┐
│                       1. CHECK                                     │
│   docker compose config --images → list of all images             │
│   docker manifest inspect <image> → remote digest                 │
│   → Compare with running digest                                   │
└─────────────────┬──────────────────────────────────────────────────┘
                  │ updates available
                  ▼
┌────────────────────────────────────────────────────────────────────┐
│                       2. BACKUP                                    │
│   • empire_data/ → tar.gz                                         │
│   • Postgres → pg_dumpall                                          │
│   • empire_registry.yaml → copy                                    │
│   • Backup ID: YYYYMMDD-HHMMSS                                     │
└─────────────────┬──────────────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────────────────────────────────┐
│                       3. APPLY                                     │
│   docker compose pull   ← all images refreshed                    │
│   docker compose up -d  ← rolling restart with healthchecks      │
│   sleep 15                                                       │
│   docker ps                   ← verify all Up/Healthy             │
└─────────────────┬──────────────────────────────────────────────────┘
                  │
                  ▼
        ┌─────────────────┐
        │  All healthy?   │
        └───┬─────────┬───┘
          YES         NO
           │           │
           ▼           ▼
       SUCCESS     ROLLBACK
                   docker compose restart
                   restore from backup
                   audit: system.update.rollback
```

## Usage

### CLI

```bash
# Check what needs updating (no changes made)
./scripts/auto_update.py check

# Apply updates with backup
./scripts/auto_update.py apply

# Show current state (docker avail, last check, backups)
./scripts/auto_update.py status

# Rollback to last backup
./scripts/auto_update.py rollback

# Install cron (daily 4 AM)
./scripts/auto_update.py schedule

# Show history
./scripts/auto_update.py history
```

### API

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/api/system/update/status` | admin/operator | Docker availability, last check, backups |
| POST | `/api/system/update/check` | admin | Check for available image updates |
| POST | `/api/system/update/apply` | admin | Backup + pull + restart (long-running) |
| POST | `/api/system/update/rollback` | admin | Restore last backup |
| GET | `/api/system/update/history` | admin/operator | Last 100 lines of update history |

### Example API calls

```bash
# Check for updates
curl -X POST http://localhost:8123/api/system/update/check \
  -H "Authorization: Bearer $TOKEN"

# Apply updates
curl -X POST http://localhost:8123/api/system/update/apply \
  -H "Authorization: Bearer $TOKEN"

# Show status
curl http://localhost:8123/api/system/update/status \
  -H "Authorization: Bearer $TOKEN"
```

## Watchtower (built-in)

Watchtower runs as a sidecar container and auto-updates based on labels:

```yaml
watchtower:
  image: containrrr/watchtower
  environment:
    WATCHTOWER_CLEANUP: 'true'
    WATCHTOWER_LABEL_ENABLE: 'true'
    WATCHTOWER_ROLLING_RESTART: 'true'
    WATCHTOWER_SCHEDULE: '0 0 4 * * *'  # 4 AM daily
    WATCHTOWER_NOTIFICATIONS: 'shoutrrr'
    WATCHTOWER_NOTIFICATION_URL: 'slack://token@channel'
```

To make a service auto-update, add the label:
```yaml
services:
  my-service:
    image: my-image:latest
    labels:
      com.empire.auto-update: "true"
```

To opt-out:
```yaml
services:
  postgres:
    image: postgres:16
    labels:
      com.empire.auto-update: "false"
```

## Notifications

Watchtower can send notifications via [shoutrrr](https://containrrr.dev/shoutrrr/) to many providers:
- Slack
- Discord
- Telegram
- Email (SMTP)
- Microsoft Teams
- Pushover
- And 70+ more

Set in `.env`:
```
WATCHTOWER_NOTIFY_URL=slack://xoxb-token@channel-name
```

Or for multiple:
```
WATCHTOWER_NOTIFY_URL=slack://xoxb-token@channel,discord://token@channel
```

## Safety guarantees

1. **Backup before apply** — every update creates a dated backup of:
   - `empire_data/` (user data, datasets, audit logs)
   - Postgres (full pg_dumpall)
   - Registry config

2. **Health check after restart** — wait 15s, verify all services Up/Healthy.

4. **Audit trail** — all actions recorded:
   - `system.update.check`
   - `system.update.apply`
   - `system.update.rollback`
   - severity `warning` or `info`

5. **Rollback path** — `.rollback` command restores last backup atomically.

6. **Admin-only mutation** — `apply`/`rollback`/`check` all require `role=admin`.

## Limitations

- **No atomic docker rollback** — `docker compose rollback` is not built-in; manual image re-tag needed
- **Watchtower doesn't backup postgres** — only updates images
- **No blue-green deploy** — single-instance restart only
- **No canary** — all-or-nothing

## Audit log example

```
[2026-10-01T23:34:47] [info] system.update.check actor=admin@empire.local
[2026-10-01T23:35:00] [warning] system.update.apply actor=admin@empire.local
  backup_id=20261001-233500, images_updated=3
[2026-10-01T23:35:25] [info] system.update.complete actor=admin
  all_healthy=true, duration_seconds=25
```

## See also

- `scripts/auto_update.py` — implementation
- `web/server.py:1599` — API endpoints
- `docker-compose.yml:828` — Watchtower config
- `runbooks/auto-update.md` — operations runbook