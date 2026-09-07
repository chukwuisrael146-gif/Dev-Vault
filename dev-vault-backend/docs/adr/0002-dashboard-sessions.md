# ADR 0002: Server-tracked dashboard JWT sessions

Status: accepted for Accounts stage 4, 2026-09-07.

## Context

The architecture requires short-lived dashboard access JWTs, rotated/revocable
refresh tokens, login eligibility checks and security auditing. Dashboard JWTs must
remain separate from email-verification tokens and future machine API keys.

## Decision

Use PyJWT with a fixed HS256 algorithm, a dedicated production secret, explicit
issuer/audience and required purpose/reference/time claims. Put token encoding in
`apps/accounts/jwt.py`, lifecycle transactions in `apps/accounts/auth_services.py`,
and HTTP/DRF adaptation in `api/v1/accounts`. No empty architectural folders are added.

One `RefreshTokenSession` represents a login and its entire rotation family. Store
only its current refresh JTI, absolute expiry, revocation/use timestamps, limited
source metadata and a keyed binding to password/email/verification state. Never
persist a raw JWT. Access tokens last five minutes; sessions expire seven days
after login by default, without sliding renewal.

Serialize lifecycle writes by locking User first and RefreshTokenSession second.
Rotating replaces the refresh JTI. Presenting an older valid refresh revokes the
family, and that revocation commits before raising a public error. Logout revokes
only the referenced session and can accept a previously rotated unexpired refresh.

Every dashboard-authenticated request checks the database session and current user.
This trades fully stateless validation for immediate rejection of subsequent
requests after logout, reuse, account disabling or credential changes. It cannot
cancel requests already in progress. No shared session cache is introduced.

All login credential/eligibility outcomes and successful session lifecycle mutations
produce account audit events. Lifecycle audit failures roll back the mutation.
Unknown-user failed login has no actor or target ID; no attempted email is stored.
Existing ORM append-only guards remain; database-role enforcement and richer
tenant/source/session audit metadata are future audit-hardening work, not claimed
as complete in this stage.

## Consequences

- Clients must coordinate refresh calls and treat lost refresh responses as a
  possible need to sign in again. No replay grace window is implemented.
- Normal refresh leaves existing access JWTs usable until expiry or revocation.
- PostgreSQL availability is required for authenticated API requests. Redis is
  required for public account-command rate limits; counter failures deny requests.
- Rotating the signing key invalidates old JWTs and session bindings. No old-key
  overlap is supported; coordinate the switch and require login again.
- Password verification does not automatically upgrade stored hashes during login.
  A future upgrade must be performed under the same user lock, never by a stale
  password-check write that could overwrite a concurrent password change.
- Django admin still uses its existing cookie authentication. Browser token storage,
  CSRF/CORS integration, account-targeted/distributed brute-force defenses, MFA and
  session-management UI are not implemented here.

## Verification

Tests cover eligibility, input limits, fixed-algorithm/claim validation, purpose
separation, rotation/replay, logout isolation, credential-state invalidation, audit
rollback and token redaction. PostgreSQL tests cover simultaneous refreshes and
refresh/logout races; a real Redis test exercises atomic counters concurrently.
See the [implementation report](../implementation-authentication.md) for results.
