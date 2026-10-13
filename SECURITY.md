# Security Policy

## Supported Versions
| Version | Supported          |
|---------|--------------------|
| 4.0.x   | ✅ Active          |
| 3.x.x   | ⚠️ Critical fixes only |
| < 3.0   | ❌ End of life      |

## Reporting a Vulnerability

**DO NOT** open a public GitHub issue for security vulnerabilities.

Email: **security@grupoan.dev** with:
- Description of the vulnerability
- Steps to reproduce
- Impact assessment

We aim to respond within 48 hours.

## Security Features

### Defense in Depth (3 Gates)
- **Gate 0**: Auth (JWT), RBAC, Rate limit
- **Gate 1**: PII redaction, Input validation
- **Gate 2**: Sandbox (AST + RLIMIT), Audit log, Tenant isolation

### PII Detection
- 12 patterns including PT-BR (CPF, CNPJ, RG, CEP, phone_br)
- Microsoft Presidio with spaCy NER
- Custom recognizers for tokens, keys

### Rate Limiting
- Redis-backed token bucket with Lua atomicity
- 5/min for login (per IP)
- 60/min for general (per token+IP)
- Exempts: /health, /docs

### Sandbox
- AST validation (blocks subprocess, ctypes, pickle, fork, etc.)
- Unix RLIMIT (CPU, memory, file size)
- SSRF protection (URL allowlist)
- Per-tenant profile isolation for browser

### Audit
- Append-only (DB trigger prevents UPDATE/DELETE)
- 365-day retention default
- PII redacted before logging

### Compliance
- OWASP ZAP pen-test in CI
- 23/23 audit checks passed
- Multi-region fail-over
- Image digest pinning (SHA256)

## Best Practices for Deployers

1. **Always set JWT_SECRET to 32+ random bytes**
   ```bash
   openssl rand -hex 32
   ```

2. **Use HTTPS in production** (TLS 1.3+)

3. **Enable rate limiting at the LB level** in addition to app

4. **Back up audit logs** — they are append-only

5. **Rotate API keys** quarterly

6. **Use a WAF** (Cloudflare, AWS WAF) in front

7. **Enable network policies** in K8s

8. **Don't run as root** — pods run as user 1000
