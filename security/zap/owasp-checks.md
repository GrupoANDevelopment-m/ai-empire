# Manual OWASP Top 10 checks for AI Empire

Beyond automated ZAP scans, AI Empire has specific attack surface that needs
manual testing. This document lists what to check, how, and how to fix.

## A01:2021 — Broken Access Control

- [ ] **Tenant isolation bypass**: try to GET `/api/leads?tenant=other-tenant` with valid JWT for tenant=acme
  - Fix: every query must use `WHERE tenant = $auth.tenant` (already enforced via `empire.security.tenant.assert_tenant_match`)
- [ ] **Tool override**: try to POST `/api/tools` with `{"name": "send_outreach", "args": {}}` without permission
  - Fix: `require_permission(Permission.SEND_OUTREACH)` (already enforced)
- [ ] **JWT tampering**: change one byte of a valid JWT, verify it fails
  - Fix: HS256 signature check (already enforced)
- [ ] **Role escalation**: try `{"role": "admin"}` in JWT body without admin secret
  - Fix: secret signing, no unsigned tokens accepted

## A02:2021 — Cryptographic Failures

- [ ] **PII in logs**: send a request with email/phone, grep audit log
  - Fix: `redact()` called before write (verified)
- [ ] **HTTP vs HTTPS**: verify ALB only accepts HTTPS (port 80 redirects)
  - Fix: ALB config redirects to 443
- [ ] **Weak TLS**: run `testssl.sh https://your-empire.example.com`
  - Fix: enforce TLS 1.2+ in CloudFront

## A03:2021 — Injection (SQLi, NoSQLi, LDAP, XSS)

- [ ] **SQLi in tool args**: POST `{"goal": "' OR 1=1 --"}` to find_leads
  - Fix: parameterized queries throughout (asyncpg with $1, $2, ...)
- [ ] **XSS in user-facing output**: LLM response with `<script>` tags
  - Fix: HTML-escape agent output in web UI
- [ ] **Prompt injection**: user says "ignore previous instructions and..."
  - Fix: system prompt hardening, output validation, audit log
- [ ] **Path traversal**: try `find_leads(goal="../../etc/passwd")`
  - Fix: validate paths against whitelist

## A04:2021 — Insecure Design

- [ ] **HITL bypass**: call `send_outreach` tool directly via API, bypassing approval
  - Fix: HITL enforced at tool layer via `orchestrator.hitl.HITLStore`
- [ ] **Rate limit bypass**: rotate IPs to exceed limit
  - Fix: rate limit by tenant+apikey, not just IP
- [ ] **Audit log deletion**: try to DELETE /var/log/ai-empire/audit.log
  - Fix: append-only table trigger in Postgres

## A05:2021 — Security Misconfiguration

- [ ] **Default secrets**: scan for `change-me`, `admin/admin`, `sk-test`
  - Fix: `.env.example` requires all secrets to be set
- [ ] **Exposed debug endpoints**: GET `/debug`, `/_status`, `/health` returns too much info
  - Fix: `health_check` returns only `{status: ok}` (verified)
- [ ] **Unnecessary ports exposed**: `docker ps` shows Postgres/Redis exposed publicly
  - Fix: internal-only compose profile
- [ ] **Missing security headers**: missing CSP, HSTS, X-Frame-Options
  - Fix: Caddy config in `config/caddy/Caddyfile`

## A06:2021 — Vulnerable & Outdated Components

- [ ] **Trivy scan on every image**: `trivy image ghcr.io/.../orchestrator:latest`
  - Fix: CI runs trivy on every PR (`.github/workflows/ci.yml::scan`)
- [ ] **Python deps out of date**: `pip-audit` against `orchestrator/requirements.txt`
  - Fix: `requirements.txt` pins exact versions, weekly Dependabot

## A07:2021 — Identification & Authentication Failures

- [ ] **Brute force JWT secret**: try common secrets
  - Fix: required SECRET_KEY 32+ chars (verified)
- [ ] **Token never expires**: verify JWT exp claim honored
  - Fix: PyJWT raises ExpiredSignatureError (verified)
- [ ] **Credential stuffing**: try leaked creds
  - Fix: rate limit + audit log + alert

## A08:2021 — Software & Data Integrity Failures

- [ ] **Supply chain attack**: verify all images pinned to digest (✓)
- [ ] **Tool result tampering**: man-in-the-middle between tool and LLM
  - Fix: TLS everywhere, signed audit log
- [ ] **Untrusted OpenAPI spec**: ZAP API scan (✓)

## A09:2021 — Security Logging & Monitoring Failures

- [ ] **No alerting on auth failures**: 100 failures/min should page
  - Fix: `EmpireAuthFailures` Prometheus alert
- [ ] **No audit retention**: audit log < 1 year
  - Fix: S3 lifecycle + Loki retention 30d + WORM if needed
- [ ] **No detection of PII leak**: redaction volume spike should page
  - Fix: `EmpirePIILeak` alert

## A10:2021 — Server-Side Request Forgery (SSRF)

- [ ] **Browse to internal IP**: agent fetches `http://169.254.169.254/` (AWS metadata)
  - Fix: navigate_browser validates URLs against private IP ranges
- [ ] **Image generation from prompt injection**: prompt "show me http://internal..."
  - Fix: ComfyUI prompts are pure text, no URL fetch

## Empire-specific attack surface

- **Tool poisoning**: attacker crafts a tool response that looks legit but contains payload
  - Defense: hash tool responses, log all, alert on anomalous patterns
- **LLM exfiltration**: user extracts system prompt via prompt injection
  - Defense: prompt hardening, version control system prompts, log
- **Multi-tenant data bleed**: one tenant's leads visible to another
  - Defense: `assert_tenant_match` on every fetch (verified)
- **Cost amplification**: attacker drives up LLM bill
  - Defense: per-tenant cost cap + circuit breaker + alert
- **Reputation damage**: agent posts offensive content on social media
  - Defense: HITL approval required for `publish_social`

## Testing schedule

| Frequency | Tests |
|---|---|
| **Every PR** | Lint + tests + secret scan |
| **Weekly** | ZAP baseline against staging |
| **Monthly** | ZAP full against staging |
| **Quarterly** | External pen-test |
| **Yearly** | Compliance audit (SOC 2, GDPR) |
