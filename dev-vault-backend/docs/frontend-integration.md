# Frontend integration contract

`docs/openapi.yaml` contains all routes and fields. `/api/v1/schema/` serves the
same contract; `/api/v1/docs/` provides an interactive viewer. The Postman collection
is a 20-request starter, not every API endpoint.

## Browser setup and sessions

Add your exact frontend origin to the existing private `.env`, for example
`CORS_ALLOWED_ORIGINS=http://localhost:5173`, and restart Django. `localhost` and
`127.0.0.1` are different origins. Do not use wildcard origins. Authentication uses
Authorization headers, not cross-origin cookies.

1. Register, deliver/preview the local verification email, and confirm the token.
2. Log in; keep the access/refresh pair private. Send `Authorization: Bearer
   <access_token>` on dashboard requests.
3. Load `GET /api/v1/me/` and `GET /api/v1/organizations/`.
4. Serialize refresh requests and replace both tokens together. A failed refresh
   requires login. Reusing an old refresh token revokes the session; refreshing
   does not extend its original seven-day lifetime.
5. Logout with the refresh token; clear frontend session state even when offline.

Prefer in-memory token storage. Persistent browser storage increases XSS exposure.
Do not send tokens to analytics/error reporting. A cookie/BFF design needs separate
CSRF/session work; do not simply switch this API to cookies. Sensitive changes
require a login within the last 15 minutes and explicit `confirm: true` where
documented. Password changes/resets revoke all sessions. Profile updates accept
first/last name only.

## Screen order

| Screen | API family |
| --- | --- |
| Accounts | `/auth/`, `/me/`, `/me/password/` |
| Organization/team | Organizations, members, invitations, ownership transfer |
| Projects/services | Organization projects, project environments, environment services |
| Keys/scopes | Environment keys, service permissions, key grants/revoke/rotate |
| Policies | Organization policies, version-checked edits and revision history |
| Usage/audit | Summaries, events, audit logs and asynchronous exports |
| Webhooks | Endpoints, signing-secret rotation, deliveries and retry |

A new project automatically has test/live environments; use their returned UUIDs.
Resource parents are immutable. Owner/admin can change live credentials; developers
are limited to test credential changes. The server always checks roles; hiding UI
controls is not authorization. Missing and foreign resources can both return 404.

## Mutations and one-time secrets

Documented create/rotation/export commands require an `Idempotency-Key`: generate
a fresh printable ASCII UUID per operation. Keep it and the identical payload only
for an exact retry. A changed payload with the same key returns 409. Never use one
global key for unrelated work.

New credential/signing secrets appear only in the initial successful response.
Show a copy-once dialog. Metadata/list/retry responses cannot recover plaintext.
If the original response is lost, revoke/rotate and issue another credential.
Never send secrets to telemetry or commit exported Postman variables.

Policy edits require `expected_version`. Reload and resolve stale-version 409s.
All applicable policies must allow a request. Rate revisions start new rate
counters; quota edits preserve consumed usage. Rotation preserves a key family's
counters and grants. Test/live counters remain separate.

## Responses and reports

Lists generally use `{next, previous, results}` and single resources `{data: ...}`.
Accounts/environment-list response shapes are explicitly described in the schema;
do not assume one universal wrapper. Errors use
`{error: {code, message, details, request_id}}`. Show field errors from `details`;
retain the request ID for support without logging credentials.

| Status | Action |
| --- | --- |
| 400 / 413 | Correct invalid or oversized input |
| 401 | Refresh dashboard authentication once, or sign in |
| 403 / 404 | Show denied/not-found without exposing another tenant |
| 409 | Resolve stale edits, command conflicts or export-not-ready |
| 429 | Respect Retry-After and rate/quota error code |
| 503 | Show temporary unavailability; never interpret as allowed |

Reports default to seven days and allow at most 93 days. Dates/quota boundaries
are UTC. The usage summary accepts `granularity=hour` (default) or `day`; the
series field `hour` is the UTC bucket start, midnight for daily results.
Exports require explicit start/end, return a queued job, then an authorized
download once ready. Poll gently. Files expire after 24 hours and are limited to
100,000 rows. Role removal also removes download access. Aggregation is asynchronous;
verification events and quota reservations are durable before an allow response.

## Server-to-server verification

The trusted customer backend owns service ID, environment, audience, required
scopes, method, unit cost and operation ID. Never let a consumer choose weaker
scopes, zero cost or a reused operation ID for fresh work.

```http
POST /api/v1/access/verify/
Authorization: Bearer <customer_api_key>
X-DevVault-Service-Token: <private_integration_credential>
Idempotency-Key: <server_owned_operation_uuid>
Content-Type: application/json
```

```json
{
  "service_id": "<service UUID>",
  "environment": "test",
  "audience": "orders-api",
  "required_scopes": ["orders:read"],
  "scope_mode": "all",
  "method": "GET",
  "units": 1
}
```

Empty scopes explicitly request authentication-only verification. Names match
exactly without wildcards. DevVault authorizes API access, not ownership of an
individual customer's record: the integrated service must still check record
ownership and business idempotency. Timeouts/5xx never authorize protected work.
The integration credential must never be placed in the dashboard browser bundle.
See [the local Python/Django SDK](../integrations/python/README.md).
