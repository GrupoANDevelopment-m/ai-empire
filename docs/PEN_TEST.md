# Pen-Test Process

AI Empire runs **automated OWASP ZAP dynamic scans** on every PR and push to `main`. Critical findings block deployment.

## What gets scanned

| Scan type | Target | What it finds |
|-----------|--------|---------------|
| Baseline | All URLs | Quick scan, headers, common vulns |
| Full | All URLs (with auth) | Deep crawl, active probing, multi-step attacks |
| API | OpenAPI spec | Endpoints, payloads, parameter injection |

## Scan configuration

- **Tool**: `zaproxy/action-baseline`, `zaproxy/action-full-scan`, `zaproxy/action-api-scan` v0.7.0
- **Trigger**: Every push to `main`/`dev`, every PR
- **Runtime**: ~10 minutes full scan, 2-3 minutes baseline
- **Failure threshold**: 0 critical, ≤ 5 high

## Running locally

```bash
# 1. Start AI Empire
./install.sh --non-interactive
./empire start

# 2. Wait for healthy
while ! curl -fs http://localhost:8123/health; do sleep 1; done

# 3. Run ZAP baseline
docker run --rm -v $(pwd)/.zap:/zap/wrk:rw \
  owasp/zap2docker-stable \
  zap-baseline.py -t http://localhost:8123 \
  -r baseline-report.html

# 4. Run ZAP full
docker run --rm -v $(pwd)/.zap:/zap/wrk:rw \
  owasp/zap2docker-stable \
  zap-full-scan.py -t http://localhost:8123 \
  -r full-report.html

# 5. View reports
open full-report.html
```

## Severity scale

| Severity | Examples | Required action |
|----------|----------|-----------------|
| **Critical** | RCE, SQLi, auth bypass, XSS-stored | Fix before merge |
| **High** | SSRF, command injection, IDOR | Fix within 1 week |
| **Medium** | Information disclosure, weak crypto | Fix within 1 month |
| **Low** | Missing headers, info leaks | Fix when convenient |
| **Informational** | Best practices, hardening hints | Track in backlog |

## Common findings + fixes

### CORS misconfiguration
**Symptom**: Access-Control-Allow-Origin: *
**Fix**: Already restricted in dev, tighten in prod via `CORS_ALLOWED_ORIGINS` env var

### Missing security headers
**Symptom**: No CSP, HSTS, X-Frame-Options
**Fix**: Add nginx reverse proxy config in `nginx/nginx.conf`

### Directory listing
**Symptom**: `/static` shows file list
**Fix**: nginx autoindex off (already done)

### Open redirect
**Symptom**: `?next=` param allows redirect to evil.com
**Fix**: Validate `next` is on same origin

## What we DON'T scan (false positives)

These are flagged by ZAP but not real vulnerabilities in our context — see `.zap/rules.tsv`:

- **CSRF token absence** — we use JWT in Authorization header, no cookies
- **Cookie HttpOnly/SameSite/Secure** — no cookies used
- **Missing X-Frame-Options on SPA** — SPA renders in iframe OK
- **SSRF on `/api/capabilities/forge/generate`** — admin-only, PII redacted

## Reporting vulns

Found a vulnerability in AI Empire?
- **Email**: security@ai-empire.example.com
- **PGP key**: in `SECURITY.md`
- **Response SLA**: 24 hours acknowledge, 7 days triage, 30 days fix

## Compliance

| Standard | Coverage | Report |
|----------|----------|--------|
| OWASP Top 10 | All A1-A10 | ZAP full scan |
| CWE Top 25 | Top 10 covered | ZAP full scan + custom checks |
| PCI-DSS 6.5 | 6.5.1-6.5.10 | ZAP + manual review |
| SOC 2 CC6 | CC6.1, CC6.6, CC6.7 | Quarterly external pen-test |

## See also

- `.zap/rules.tsv` — exclusion rules
- `.github/workflows/ci.yml:199-280` — CI integration
- `SECURITY.md` — disclosure process