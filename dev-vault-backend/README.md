# DevVault backend

A modular Django backend for API access management. The authoritative design is
[DEVVAULT_ARCHITECTURE.md](DEVVAULT_ARCHITECTURE.md).

The combined MVP is implemented for local frontend integration: Accounts and
password recovery, organizations/roles/invitations, projects/test-live environments,
services, one-time credentials and rotation, scopes, versioned rate/quota policies,
trusted server verification, usage/audit reporting, CSV exports and signed webhooks.
Production release still requires the gates in [the runbook](docs/operations.md).
See [the implementation report](docs/backend-implementation-report.md) for evidence
and explicit exclusions; this is not the entire future enterprise roadmap.

## Local development (Windows Command Prompt)

```bat
venv\Scripts\activate
set DJANGO_READ_ENV_FILE=true
docker compose up -d redis
python manage.py migrate
python manage.py runserver
```

Use the existing `.env`; for a new checkout, copy `.env.example` and supply local
database credentials and a random secret key. Never commit the real `.env`.
The `DJANGO_READ_ENV_FILE` shell variable must be set in each new terminal.
The current project uses your locally installed PostgreSQL; do not start a second
PostgreSQL service on port 5432. Redis must be running for account API throttling.

For a fresh environment use Python 3.14 and the tested dependency constraints:

```bat
python -m pip install -r requirements/development.txt -c requirements/constraints.txt
```

## Verification emails

Registration queues an email. In development, deliver it to an ignored local file:

```bat
python manage.py deliver_account_emails
python manage.py preview_email --open
```

The preview command decodes the latest email and opens its confirmation link.
Click **Verify email**; do not copy an encoded MIME fragment as the token.
Development never sends these messages to a real inbox. Celery worker + beat can
process the same queue automatically in Linux/WSL2.

See [the endpoint and setup guide](docs/api/email-verification.md) and
[the verification design decision](docs/adr/0001-email-verification.md).

## Login and sessions

After verifying an account, use these JSON endpoints:

- `POST /api/v1/auth/login/`: email and password; returns access/refresh tokens.
- `POST /api/v1/auth/refresh/`: current refresh token; returns a replacement pair.
- `POST /api/v1/auth/logout/`: refresh token; revokes that session.

Access tokens last five minutes; a refresh session lasts seven days from login.
Use `Authorization: Bearer <access_token>` on protected dashboard API requests.
Send refresh requests one at a time and replace both tokens after every successful
refresh. Reusing a previous refresh token revokes the whole session, requiring login.

The existing private `.env` was not modified. Local development can derive its JWT
key from `DJANGO_SECRET_KEY`; production must supply a separate random
`ACCOUNT_JWT_SIGNING_KEY` of at least 32 bytes. See `.env.example` for settings.

See [the authentication guide](docs/api/authentication.md),
[the session design decision](docs/adr/0002-dashboard-sessions.md) and
[the implementation and verification report](docs/implementation-authentication.md).

## Checks

```bat
python manage.py check
python -m pytest -q
```

Fast tests use temporary SQLite data, an in-memory mailbox and a memory cache.
The optional PostgreSQL test settings exercise transaction locking in a dedicated
test database. The opt-in Redis integration test uses only a uniquely prefixed
temporary counter; instructions are in the authentication guide.
Health endpoints: `/api/v1/health/live/` and `/api/v1/health/ready/`.

## Frontend and background work

For real registration and password-reset delivery, see [account email setup](docs/email-delivery.md).
Development saves emails to files unless `DJANGO_EMAIL_MODE=smtp` is explicitly configured.
`check_email_connection` checks SMTP without sending; `deliver_account_emails --watch`
processes both account queues locally. A queued response is not proof of inbox delivery.

Start with [the frontend integration guide](docs/frontend-integration.md).
The complete [OpenAPI contract](docs/openapi.yaml) is also available at
`/api/v1/schema/`; browse `/api/v1/docs/` after starting the server.
Import [the Postman starter](docs/devvault.postman_collection.json) for onboarding.
Current-user/profile and password endpoints now exist at `/api/v1/me/` and
`/api/v1/me/password/`. Password changes/resets revoke all sessions.

Dashboard authentication uses JWTs. Customer verification uses an API key **plus
a separate private server integration credential**. Never put that credential
in the browser bundle. See [the Python/Django SDK](integrations/python/README.md).

Run `deliver_invitations` and `aggregate_usage` locally as needed. Celery worker
and a single beat scheduler process periodic mail, aggregation, exports and webhook
jobs in Linux/WSL2 or containers. Webhook network delivery is disabled by default.
For a local manual export pass (no outbound webhooks):

```bat
python manage.py shell -c "from apps.usage.exports import process_usage_exports; from apps.audit.tasks import process_audit_exports; process_usage_exports(); process_audit_exports()"
```

Use `python manage.py reconcile_usage` for a read-only ledger check.
Use `python manage.py cleanup_exports` to preview expired CSV cleanup; `--apply`
removes expired generated files, not source usage/audit facts.

## Full verification

```bat
python manage.py makemigrations --check --dry-run
python -m ruff check .
python -m ruff format --check .
python -m pytest -q --cov --cov-report=term-missing
python manage.py spectacular --settings=config.settings.test --file docs/openapi.yaml --validate --fail-on-warn
python scripts/check_secrets.py
```

Run `./scripts/test_postgresql.ps1` in PowerShell for real PostgreSQL/Redis tests.
It uses PostgreSQL 18 binaries and a disposable cluster on port 55439, then stops
and removes only that cluster after success. Redis tests use database 15 and
delete only their UUID-namespaced keys. No development database is flushed or
application role granted CREATEDB. See the runbook for backup/restore rehearsal.

For PowerShell setup, use `$env:DJANGO_READ_ENV_FILE = 'true'` instead of `set`.
Run commands from `dev-vault-backend`. Keep your existing private `.env`; changing
the development secret key invalidates credentials derived from its defaults.

## Code map

`config/settings/` owns environment configuration; `api/v1/` owns HTTP delivery.
Domain services/selectors live in `apps/accounts`, `organizations`, `projects`,
`credentials`, `access`, `usage`, `audit` and `webhooks`. `apps/core` supplies shared
primitives, errors, logging and health. Tests and migrations stay near their apps.
Only useful folders were added; the architecture diagram was not copied into empty
scaffolding. Start the frontend with Accounts and organization/project onboarding,
then key management, policies, usage and audit screens.
