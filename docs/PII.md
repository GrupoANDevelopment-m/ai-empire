# AI Empire — PII Policy

## What is PII

Personally identifiable information: anything that can identify a natural
person. Includes but not limited to:

- Email addresses
- Phone numbers (any country)
- Credit card numbers
- Government IDs (SSN, IBAN, CPF, etc.)
- IP addresses
- Names combined with other identifiers
- Conversation transcripts containing any of the above

## How we handle PII

1. **Redaction** — before writing anything to the audit log or persisting
   it to a vector DB, PII patterns are redacted via `empire.security.pii`.
   Patterns are configurable via `PII_REDACT` env var.

2. **No PII in prompts** — the agent is instructed to never include raw
   PII in prompts to third-party LLMs unless the user has explicitly
   opted in (via `FEATURE_SEND_PII=true`).

3. **Retention** — conversation history is auto-deleted after
   `PII_RETENTION_DAYS` (default 30). Leads data is kept for 90 days by
   default unless the user requests deletion.

4. **Opt-out** — every API request can include header `X-No-PII-Log: true`
   to skip the audit log entirely. The UI has a "private mode" toggle.

5. **Right to erasure** — `DELETE /api/users/{id}` deletes the user, all
   their sessions, all leads attributed to them, and all audit entries
   referencing them. Returns a signed receipt.

## Roles

- **DPO (Data Protection Officer)** — first point of contact for data
  subject requests. Configure via `DPO_EMAIL` env var.
- **Security Officer** — handles breach response.
- **Engineers** — must not log raw PII; use `redact()`.

## Breach response

1. Containment: stop the affected service immediately.
2. Assess scope: query `audit_log` for the time window.
3. Notify: DPO, Security Officer, legal (within 72h for GDPR).
4. Remediate: rotate any leaked secrets, notify affected users.
5. Post-mortem: write incident report within 14 days.

## Data subject rights (GDPR)

| Right | How to exercise |
|---|---|
| Right to access | `GET /api/users/{id}/export` returns all data we hold |
| Right to erasure | `DELETE /api/users/{id}` |
| Right to rectification | `PATCH /api/users/{id}` |
| Right to portability | `GET /api/users/{id}/export?format=jsonld` |
| Right to object | `POST /api/users/{id}/object` |

## Compliance frameworks

- **GDPR** (EU): see above
- **CCPA** (California): same as GDPR + opt-out of sale
- **HIPAA** (US health): BAA required with all subprocessors, encrypt at rest
- **LGPD** (Brazil): similar to GDPR

## Subprocessors

When delegating to third-party LLMs (Anthropic, OpenAI, etc.), their
privacy policies apply. We commit to:

1. Document each subprocessor in `docs/SUBPROCESSORS.md`
2. Allow user to opt out of each one
3. Use EU-resident endpoints for EU users when available
4. Sign DPAs with all paid providers
