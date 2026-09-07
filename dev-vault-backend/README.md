# DevVault backend

A modular Django backend for API access management. The authoritative design is
[DEVVAULT_ARCHITECTURE.md](DEVVAULT_ARCHITECTURE.md).

Implemented so far: shared UUID/timestamp models, settings split, PostgreSQL/Redis
configuration, Celery integration, health endpoints, safe API errors/logging,
email-based users, registration and single-use email verification with resends,
durable mail delivery, throttling and account audit records. Dashboard authentication
now includes login, short-lived access JWTs, rotated refresh tokens and logout.

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

For a fresh environment, install `requirements/development.txt`. This authentication
stage adds PyJWT (`>=2.13,<3`), already installed in the current virtual environment.

```bat
python -m pip install -r requirements/development.txt
```

## Verification emails

Registration queues an email. In development, deliver it to an ignored local file:

```bat
python manage.py deliver_verification_emails
```

Open the latest email in `var/emails/`, follow its link and click **Verify email**.
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

Next: Accounts stage 5 — current-user and password endpoints. There is no `/me/`
endpoint yet; the authentication tests use a test-only protected route.
