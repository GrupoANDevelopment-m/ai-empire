# Auto-Update Runbook

## Routine

### Daily (4 AM) — automated
- Watchtower runs, pulls new images, restarts containers with health checks.
- Notifications sent if any update fails.

### Weekly — manual review
```bash
./scripts/auto_update.py status
./scripts/auto_update.py history | tail -50
```

## Emergency: bad update deployed

1. Identify which service broke:
   ```bash
   docker ps | grep -v healthy
   docker logs <container>
   ```

2. Rollback the most recent update:
   ```bash
   ./scripts/auto_update.py rollback
   # Or via API:
   curl -X POST http://localhost:8123/api/system/update/rollback \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

3. If rollback fails (corrupt backup), pin to known-good digest:
   ```bash
   # Edit docker-compose.digests.yml
   # Find the service, replace :latest with :sha256:<known-good>
   docker compose -f docker-compose.yml -f docker-compose.digests.yml up -d
   ```

4. Investigate root cause:
   - Check release notes for the new image version
   - Test the image locally: `docker run --rm <image> <entrypoint>`
   - Open an issue with the upstream image

## Disable auto-update for a service

```yaml
# docker-compose.yml
my-critical-service:
  image: my-image:latest
  labels:
    com.empire.auto-update: "false"
```

Or pin to a digest:
```yaml
my-service:
  image: my-image@sha256:abc123...
```

## Manual update

```bash
# Check what would be updated
./scripts/auto_update.py check

# Apply with backup
./scripts/auto_update.py apply

# Or via API
curl -X POST http://localhost:8123/api/system/update/apply \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Notifications not working

```bash
# Test shoutrrr URL
docker run --rm containrrr/shoutrrr send \
  -u "$WATCHTOWER_NOTIFY_URL" \
  -m "test from shoutrrr"

# Check Watchtower logs
docker logs ai-empire-watchtower
```

## Backup integrity check

```bash
# List backups
ls -la logs/updates/backups/

# Inspect specific backup
tar -tzf logs/updates/backups/20261001-233500/empire_data.tar.gz | head

# Restore manually (if auto rollback fails)
tar -xzf logs/updates/backups/20261001-233500/empire_data.tar.gz
```

## References

- Watchtower docs: https://containrrr.dev/watchtower/
- Shoutrrr (notifications): https://containrrr.dev/shoutrrr/
- `docs/AUTO_UPDATE.md` — architecture overview