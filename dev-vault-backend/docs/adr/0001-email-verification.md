# Email verification and durable mail delivery

Status: accepted for Accounts stage 3, 2026-09-07.

## Decision

Accounts owns an `EmailVerificationToken` record containing an opaque UUID, user,
email snapshot, expiry, consumption/invalidation timestamps and email delivery state.
It stores no bearer token. Django's SHA-256 `Signer` signs the UUID using the project's
secret key and a purpose-specific salt bound to the user's password hash. Changing
the password invalidates previously delivered signatures. Verification additionally
checks the stored email against the current email, expiry, pending status, `is_active`,
and whether the record was already consumed or invalidated. Secret-key rotation
uses Django's `SECRET_KEY_FALLBACKS` convention if an overlap is deliberately configured.

Links expire after 30 minutes by default. A resend invalidates the previous reference;
there is one open reference per user, a 60-second cooldown and a five-per-hour account
limit including the initial email. The resend API returns the same 202 response for
unknown, ineligible and suppressed accounts. The existing registration 409 duplicate
response is retained for compatibility; registration therefore still reveals existence.

Issuance, consumption and delivery lock the user row before the verification row.
Consumption and activation are one transaction. PostgreSQL row locks and a partial
unique constraint protect parallel requests. These guarantees require PostgreSQL;
SQLite is used only for the fast tests.

The verification record also acts as a small, Accounts-specific transactional outbox.
Registration commits the user, pending email and audit events together. A Celery beat
task drains committed pending records every 30 seconds. This deliberately avoids
publishing to the broker during registration or relying solely on an on-commit callback:
a broker outage or web-process crash cannot lose an already committed mail request.
Tasks call domain services and have no email address or token in their payload.
No generic event bus or empty architectural modules are introduced.

SMTP delivery is at least once: a crash after SMTP acceptance but before committing
`sent_at` may duplicate the same link. Ordinary overlapping workers serialize and skip
delivered messages. External SMTP cannot participate in the database transaction.
Delivery holds the user/reference locks during the bounded (10-second timeout) send;
monitor this tradeoff if volume grows. Transient mail errors are retried up to five
times with exponential backoff and jitter; expired/ineligible records are never sent.
After exhaustion the user can request a fresh link within the resend limits.

`apps.audit` starts with append-only account facts, storing only opaque references and
request IDs, in the same transaction as security changes. Organization scoping and
audit querying remain future domain work. Model/queryset guards protect product writes;
production database roles should additionally deny UPDATE/DELETE on audit tables.
No product audit mutation endpoints exist. Raw SQL/database-administrator access is
not made immutable by ORM guards.

## HTTP and secrets

The email uses the configured public origin, never a client-controlled Host header.
Its token is in the URL fragment. The confirmation page removes the fragment from
browser history and submits it in a JSON POST only after an explicit button click.
GET does not consume tokens, so mail scanners cannot activate an account by fetching
the link. The page uses no third-party scripts, a nonce-based CSP, no-referrer and
no-store headers. Logs redact the new token prefix, including percent-encoded forms.

Account POST endpoints use atomic Redis fixed-window counters based on REMOTE_ADDR.
Forwarded headers are ignored; a trusted reverse proxy must provide a validated client
address at deployment or all users share the proxy's limit. Fixed windows permit a
burst across the window boundary. Cache outages return a safe 503 instead of allowing
unlimited account requests. These are separate from future API-consumer access limits.

## Delivery modes and operations

Development writes emails to the ignored `var/emails/` directory. Test mode uses an
in-memory mailbox. Production uses configured SMTP over TLS. Only test messages are
sent during automated checks. No SMTP credentials are guessed or copied into source.

Operate exactly one beat scheduler. Monitor pending records with five failed attempts
and oldest pending age; they are not automatically deleted. Verification records contain
email snapshots: purge expired/consumed/invalidated rows after a chosen operational
retention period (recommended seven days) before public production use. Local mailbox
files are sensitive and should be cleared after testing. Audit retention is separate.

## Remaining sequence

Stage 4 adds login, short-lived JWT access tokens, refresh rotation, session revocation
and logout. Stage 5 adds current-user/password workflows. Neither is implemented here.
