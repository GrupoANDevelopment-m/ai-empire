# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 3.4.x   | :white_check_mark: |
| 3.3.x   | :white_check_mark: |
| 3.2.x   | :x:                |
| < 3.2   | :x:                |

## Reporting a Vulnerability

We take security seriously. Report vulnerabilities to:

**security@ai-empire.example.com** (PGP key below)

Please **DO NOT** open a public GitHub issue for security vulnerabilities.

### What to include

- Description of the vulnerability
- Steps to reproduce
- Impact assessment (what data/systems affected)
- Affected versions
- Your name/handle for credit (optional)

### Response SLA

| Stage | Time |
|-------|------|
| Acknowledgement | 24 hours |
| Initial triage | 7 days |
| Patch in main | 30 days |
| Public disclosure | 90 days (or when fix is deployed) |

## Security Features

### Built-in

- **JWT authentication** (HS256, ≥32 byte secret enforced)
- **RBAC** with 3 roles (admin, operator, viewer)
- **Tenant isolation** via ContextVar
- **Rate limiting** (Redis token bucket, 60/min default)
- **PII auto-redaction** (9 patterns: email, CPF, credit card, etc)
- **Append-only audit log** with PII redaction
- **Sandbox for untrusted code** (AST + RLIMIT + SSRF protection)
- **Input validation** (max message length, max page size, max file size)
- **CORS restricted** (configurable via env var in prod)

### Operational

- **OWASP ZAP pen-test** on every CI build
- **Auto-update** with backup + rollback
- **Multi-region failover** via Route 53
- **Daily backups** to S3 (cross-region, versioned)
- **CloudWatch alarms** for instance health
- **Encrypted at rest** (EBS, RDS, S3)
- **TLS 1.3 only** on ALB
- **IMDSv2 required** (no metadata theft)

## Security Audits

| Year | Auditor | Report |
|------|---------|--------|
| 2026-Q1 | (planned) External firm | TBD |
| 2025-Q4 | Internal | docs/audits/2025-q4.md |

## Hall of Fame

Researchers who reported valid vulnerabilities:
- *(no entries yet)*

## PGP Key

```
-----BEGIN PGP PUBLIC KEY BLOCK-----
[Will be filled in before public release]
-----END PGP PUBLIC KEY BLOCK-----
```

## References

- `docs/PEN_TEST.md` — pen-test process
- `docs/SECURITY_MODEL.md` — threat model
- `runbooks/incident-response.md` — incident handling