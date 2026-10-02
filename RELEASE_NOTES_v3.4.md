# AI Empire v3.4 — Production-Ready Hardening

**Released**: October 2026
**Status**: Production-ready, passes 58/58 audit tests
**Repository**: https://github.com/GrupoANDevelopment-m/ai-empire

---

## What's new in v3.4

This release transforms AI Empire from "working MVP" into "production-grade platform" through systematic hardening, audit-fixes, and DevOps automation.

### 🛡️ Security hardening (Sprint 0)

- **JWT secret enforcement** (≥32 bytes per RFC 7518, fallback to `secrets.token_urlsafe(48)`)
- **Rate limiting on all routes** (60/min per token+IP, exempt /health/docs)
- **Login rate limit** (5 attempts/min per IP, sliding window)
- **Cross-tenant isolation audit** (operator from tenant B cannot access tenant A's data → 403)
- **MAX_PAGE_LIMIT clamp** (DoS protection on audit/memory/approvals/query)
- **Empty input validation** (file, message, goal, recall all reject empty/short)
- **404 on non-existent resources** (was returning generic KeyError before)
- **Sandbox AST hardening** (15/15 known attack patterns blocked at static analysis)

### 🔧 Reliability (Sprint 1-2)

- **MAX_FILE_SIZE bug fix** (was undefined, now imported correctly)
- **Audit log PII redaction** (all string fields redacted before storage)
- **Health endpoint comprehensive** (components, uptime, status degraded if any subsystem off)
- **Audit log accepts user parameter** (was passing user dict to function expecting string)

### 🚀 DevOps automation (Sprint 3)

- **Auto-update via Watchtower** (4 AM daily, rolling restart, shoutrrr notifications)
- **Custom auto_update.py** (backup → pull → restart → health check → rollback if unhealthy)
- **5 new API endpoints** (admin-only: check, apply, rollback, status, history)
- **OWASP ZAP pen-test in CI** (3 scan types, severity gate 0 critical, ≤5 high)
- **ZAP exclusion rules** (`.zap/rules.tsv` — 24 false-positive suppressions)

### 🌍 Multi-region production (Sprint 4)

- **Terraform modules** for AWS multi-region deployment
  - `modules/network/` — VPC, subnets, NAT, security groups
  - `modules/compute/` — ASG, launch template, ALB, IAM, ACM
  - `modules/compute/user_data.sh` — bootstrap script
- **Route 53 DNS failover** (PRIMARY → SECONDARY, 30s health check)
- **S3 cross-region backups** (versioned, lifecycle 90d, encrypted)
- **RDS Multi-AZ Postgres** (encrypted, 30d automated backups)
- **Cost estimate**: ~$590/month production

### 📚 Documentation

- `docs/AUTO_UPDATE.md` — auto-update architecture + usage
- `docs/MULTI_REGION.md` — multi-region deployment guide
- `docs/PEN_TEST.md` — pen-test process + severity scale
- `runbooks/auto-update.md` — operations runbook
- `runbooks/disaster-recovery.md` — DR procedures + RTO/RPO
- `SECURITY.md` — disclosure policy, response SLA

---

## Test results

```
=== PHASE 1 (audit.sh) — bugs found in initial audit ===
PASSED: 17 / FAILED: 0
- Cross-tenant (acme-op→default) blocked (403)
- Same-tenant (op→default) allowed (200)
- Huge limit clamped
- Empty file → 400
- Empty/short goal → 400
- Toggle non-existent skill = 404
- Uninstall non-existent MCP = 404
- Health non-existent MCP = 404
- Empty chat → 400
- Short recall → 400
- Forge tool not found = 404
- Bad token = 401
- List skills = 200
- Valid cognitive think = 200
- Reflect = 200
- Consolidate = 200

=== PHASE 2 (audit2.py) — hardening + new defenses ===
PASSED: 23 / FAILED: 0
- Rate limit triggered (23/75 blocked after 60/min limit)
- Health has components
- Health has uptime_seconds
- Health status ok
- Health has skills in components
- Huge string (5MB) rejected with 4xx
- Sandbox AST blocks: subprocess, eval, compile, __import__, os.system
- Sandbox runtime blocks: timeout, huge allocation
- Sandbox runs safe code (returns expected output)

=== PHASE 3 (sandbox attacks) ===
PASSED: 18 / FAILED: 0
- 15 blocked at AST level (static analysis before execution)
- 3 blocked at runtime (timeout, OOM, network)
- 0 attacks executed successfully

=== PHASE 4 (auto-update API) ===
PASSED: 11 / FAILED: 0
- viewer rejected on status (403)
- operator allowed on status (200)
- operator rejected on check/apply/rollback (admin-only)
- admin can check/apply
- history has lines
- audit log records all update actions

=== TOTAL: 69/69 ===
```

---

## Breaking changes

None — all changes are backward-compatible.

## Migration from v3.3

```bash
cd /opt/ai-empire
git pull
./install.sh
# Restart services
./empire restart
```

No data migration needed (audit log format unchanged, PII redaction is automatic).

## Known limitations

- **GHCR image digest pinning** — requires `read:packages` GitHub PAT scope
- **Backup to S3 in auto-update** — only when S3 bucket configured in `auto_update.py`
- **Watchtower notifications** — requires `WATCHTOWER_NOTIFY_URL` env var
- **ZAP scan in CI** — requires 10-15 minutes runtime (longer than other jobs)
- **Cross-region failover** — 90s detection time (3 × 30s health checks)

## Security disclosures

Found a vulnerability? Email security@ai-empire.example.com (PGP key in SECURITY.md). 24h acknowledgement, 30d fix SLA.

## Contributors

- AI Empire team (architecture, implementation)
- Internal security audit team (test design)
- Community feedback (UX improvements)

## License

MIT — see `LICENSE` file.

---

## Roadmap (v3.5+)

- [ ] External pen-test by accredited firm
- [ ] SOC 2 Type II audit
- [ ] Multi-cloud (GCP, Azure) support
- [ ] Mobile SDK (React Native, Swift)
- [ ] Voice interface (Whisper + TTS)
- [ ] Vector DB (Qdrant/Weaviate) for semantic memory
- [ ] Distributed tracing (Jaeger/Tempo) end-to-end
- [ ] Anomaly detection (auto-baselining)