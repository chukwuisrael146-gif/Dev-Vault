# Dashboard authentication: Accounts stage 4

These endpoints authenticate people using the DevVault dashboard. They do not
authenticate API consumers; DevVault API keys remain a separate domain.
Use JSON request bodies and HTTPS outside local development. All paths end in `/`.

## Login

`POST /api/v1/auth/login/`

```json
{"email": "person@example.com", "password": "<your password>"}
```

The email is normalized. Passwords are not trimmed and are limited to 1,024
characters, matching registration. The user must be active, have ACTIVE status,
and have verified their email. A successful request returns HTTP 200:

```json
{
  "data": {
    "access_token": "<access JWT>",
    "refresh_token": "<refresh JWT>",
    "expires_in": 300,
    "refresh_expires_in": 604800,
    "token_type": "Bearer",
    "user": {
      "id": "<user UUID>",
      "email": "person@example.com",
      "status": "active",
      "email_is_verified": true,
      "created_at": "<ISO-8601 timestamp>"
    }
  }
}
```

Lifetimes are remaining seconds at issuance. Each login creates an independent
server-tracked session. Unknown emails, incorrect passwords, unverified accounts
and disabled accounts share HTTP 401 `invalid_credentials` and the message
`Email or password is incorrect.` A successful login updates `last_login`.

Login success and credential/eligibility failures are audited. Invalid request
shapes and throttled attempts do not run the login service. Unknown-email failures
use a null audit target; passwords, attempted emails and JWTs are not audit payloads.

## Authenticate dashboard requests

```http
Authorization: Bearer <access_token>
```

Protected DRF endpoints use this authentication by default. Refresh JWTs, API keys,
Basic authorization and Django session cookies are not accepted as dashboard API
credentials. Django admin retains its separate session-cookie login.

There is no current-user endpoint yet: `/me/` is scheduled for Accounts stage 5.
Tests exercise a protected route defined only in the test module.

## Refresh

`POST /api/v1/auth/refresh/`

```json
{"refresh_token": "<current refresh JWT>"}
```

Returns HTTP 200 with `data.access_token`, `data.refresh_token`, `data.expires_in`,
`data.refresh_expires_in` and `data.token_type`. It does not return `data.user`.
No access-token header is required, so an expired access token cannot block refresh.

On each success, replace both stored tokens. Only the newest refresh token is
usable. The session expiry is absolute: refreshing does not extend the original
seven-day session. Access expiry is capped at session expiry.

Serialize refresh calls, including across browser tabs. Replaying an older,
correctly signed and unexpired refresh token revokes that session, including tokens
issued by its latest refresh. Two simultaneous requests with the same refresh
token cause one rotation followed by revocation, not two usable token pairs.
If the refresh response is lost, retrying the old token triggers the same rule:
sign in again. There is deliberately no replay grace period.

An ordinary successful refresh does not invalidate previously issued access tokens;
they remain usable until expiry or session invalidation. Refresh tokens are limited
to 4,096 characters in requests.

## Logout

`POST /api/v1/auth/logout/`

```json
{"refresh_token": "<refresh JWT for this session>"}
```

Returns HTTP 204 with no response body. Only that session is revoked; other logins
are unaffected. Clear the local tokens on success. The request is idempotent for a
valid, unexpired token whose session has already been revoked. An older rotated
refresh token may still terminate its own session. Expired, forged, wrong-purpose
or unknown-session tokens return HTTP 401 `invalid_token`.

Protected requests check the session and current user in PostgreSQL each time.
Logout, refresh-reuse revocation, disabling the user, password/email changes or
removing email verification therefore reject subsequent authenticated requests.
They do not cancel a request that has already authenticated and is executing.

## Errors and abuse limits

Errors retain the project's envelope:

```json
{
  "error": {
    "code": "invalid_token",
    "message": "The token is invalid or expired. Please sign in again.",
    "details": {},
    "request_id": "<correlation ID>"
  }
}
```

Login/refresh/logout responses, including errors, use `Cache-Control: no-store`
and `Pragma: no-cache`. HTTP 401 includes a Bearer `WWW-Authenticate` challenge.
Missing/invalid input returns HTTP 400 `validation_error`.

Redis enforces fixed-window limits per direct client IP: login 20 per five minutes,
refresh 60 per minute and logout 60 per minute. Exceeded limits return HTTP 429
and `Retry-After`. An unavailable counter returns HTTP 503
`account_security_unavailable`; enforcement never silently disables itself.
The application deliberately does not trust forwarded client-IP headers. Before
placing it behind a proxy, define trusted proxy/IP handling and edge limits so all
users are not treated as the same proxy IP. Distributed brute-force defenses and
account-targeted limits remain production hardening work.

## Configuration and key rotation

The private `.env` was preserved. `.env.example` documents:

| Variable | Default / requirement |
| --- | --- |
| `ACCOUNT_JWT_SIGNING_KEY` | Derived from `DJANGO_SECRET_KEY` only for development; production requires an independent random key of at least 32 bytes |
| `ACCOUNT_JWT_ISSUER` | `devvault` |
| `ACCOUNT_JWT_AUDIENCE` | `devvault-dashboard` |
| `ACCOUNT_ACCESS_TOKEN_SECONDS` | 300; accepted range 1–900 |
| `ACCOUNT_REFRESH_TOKEN_SECONDS` | 604800; greater than access lifetime, at most 2592000 |

HS256 is fixed in code. Validation requires issuer, audience, token kind, canonical
UUID user/session/token references, and valid issue/not-before/expiry claims.
Algorithms from incoming token headers never select the verification algorithm.
PyJWT performs the cryptographic operations; custom services handle lifecycle rules.

To rotate the key, provision a fresh random value through your secret manager and
coordinate all web processes to switch together. Restart them and have users sign
in again. The old key is not retained: old JWT signatures and old session credential
bindings stop validating. Rolling mixed-key processes will cause authentication
failures until consistent. Production must not rely on the development fallback.

No JWT or raw password is stored in the session table. It contains the current
refresh identifier, expiry/revocation metadata and a keyed credential-state hash.
Existing session rows without that hash cannot authenticate; sign in again.

Keep tokens out of URLs, screenshots, application logs and analytics. The API sets
no token cookies; a browser token-storage/CSRF strategy belongs to the future
dashboard integration. Never commit tokens or real environment secrets.

## Local use and checks (Windows Command Prompt)

Run from `C:\Users\Israel Chukwu\Desktop\dev-vault\dev-vault-backend`:

```bat
venv\Scripts\activate
set DJANGO_READ_ENV_FILE=true
docker compose up -d redis
python manage.py migrate
python manage.py check
python manage.py runserver
```

Keep Docker Desktop running. PostgreSQL remains your existing local installation;
do not start the Compose PostgreSQL service on its occupied port 5432.
Register and verify an account using the [verification guide](email-verification.md),
then use the JSON bodies above in your API client. A Celery worker is not needed for
login/refresh/logout. Verification emails can be delivered with the existing local
management command.

Fast suite:

```bat
python -m pytest -q
```

Full integration suite, using a dedicated disposable PostgreSQL instance with a
test-only role allowed to create databases and an accessible Redis service:

```bat
set TEST_DATABASE_URL=postgresql://test_user:test_password@127.0.0.1:55439/postgres
set TEST_REDIS_URL=redis://127.0.0.1:6379/0
python -m pytest --ds=config.settings.postgresql_test_settings --create-db -q
```

Never use a production PostgreSQL server. The test database name is
`test_devvault_email_verification` (shared with stage 3). Four locking tests require
PostgreSQL. The opt-in Redis test uses a unique key prefix and deletes only its own
expiring counter; it does not clear your Redis database. Other tests use memory
cache/mailbox settings and send no real email.
