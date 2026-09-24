# Runbook: PII Leak Suspected

**This is a SEV-1 incident.** A PII leak requires immediate response under GDPR (notify within 72 hours).

## First 15 minutes

1. **Contain**: disable the affected log/endpoint immediately.
   ```bash
   # Disable audit log writes
   export PII_AUDIT_LOG=false
   docker compose restart langgraph-orchestrator
   ```

2. **Identify scope**:
   ```sql
   SELECT ts, actor, action, target, args, result_summary
   FROM audit_log
   WHERE
     args::text ~* 'email|phone|ssn|cc|iban'
     OR result_summary ~* 'email|phone|ssn'
     AND ts > now() - interval '24 hours'
   ORDER BY ts DESC;
   ```

3. **Stop the leak**: revoke any compromised API keys, rotate secrets.
   ```bash
   ./scripts/rotate-secret.sh POSTGRES_PASSWORD
   ./scripts/rotate-secret.sh LITELLM_MASTER_KEY
   ```

## First hour

1. **Notify DPO** (configured via `DPO_EMAIL` env var).
2. **Notify legal** — they decide whether supervisory authority notification
   is required (GDPR Art. 33).
3. **Preserve evidence** — copy `audit_log` table snapshot to a
   write-once bucket. Do NOT delete.

## First 24 hours

1. **Identify affected users** from the audit query.
2. **Send notifications** to affected users (template in
   `docs/templates/breach-notification.md`).
3. **Patch the leak**: identify the code path that wrote PII unredacted.
   File a ticket.

## First 72 hours

1. **File regulatory notification** if required (legal handles).
2. **Post-mortem** within 7 days.
3. **Update PII policy** if the incident exposed gaps.

## Prevention

- All new code that handles user data must call `redact()` before
  logging. Add a linter rule:
  ```python
  # .flake8 or ruff rule
  "audit": "B001",  # ban bare `print` in audit-touching modules
  ```
- Quarterly: grep production logs for unredacted PII patterns.
- Annual: third-party audit of PII handling.

## Contacts

- DPO: `${DPO_EMAIL}` (env var)
- Legal: `${LEGAL_TEAM_EMAIL}`
- Security: `${SECURITY_TEAM_EMAIL}`
- On-call: see `docs/ONCALL.md`
