# Accounts email verification

All JSON errors use the existing `error` envelope with `code`, `message`, `details`
and `request_id`. No verification token is returned in an API response.

## Registration

`POST /api/v1/auth/register/` retains its existing email/password/confirmation contract
and 201 response. It now creates a pending verification email in the same transaction.
The account remains pending until verification. Email delivery can occur later.

## Resend

`POST /api/v1/auth/resend-verification/`

```json
{"email": "person@example.com"}
```

Response: 202 for all well-formed requests within the IP limit, including unknown,
already verified, disabled or inactive accounts and cooldown suppression:

```json
{"message": "If this account needs verification, an email will be sent shortly."}
```

Resends use a 60-second per-account cooldown and five issuance requests per hour.
A successfully issued replacement invalidates the previous link.

## Verify

`GET /api/v1/auth/verify-email/` serves a confirmation page. Open the full link from
the email, including `#token=...`, and click **Verify email**. Merely opening it does
not activate the account. This page works without the rest of the dashboard.

`POST /api/v1/auth/verify-email/`

```json
{"token": "<token from your verification email>"}
```

Response: 200

```json
{"message": "Email verified successfully. You can now sign in."}
```

The token is single-use and expires after 1,800 seconds by default. Invalid, forged,
expired, replaced and consumed tokens return 400 `invalid_verification_token` with
the same public message. Changed-email, changed-password, disabled and inactive
accounts cannot use an old token. A missing/oversized token returns 400
`validation_error`. Verification does not create a login session or return JWTs;
use the separate [login endpoint](authentication.md) after verification.

## Abuse limits

Redis applies per-IP limits: registration 10/hour, resend 10/hour and verification
30/minute. Exceeded limits return 429 with `Retry-After`. If Redis cannot enforce
the counter, account POST endpoints return 503 `account_security_unavailable`.

## Local walkthrough (Command Prompt)

In the activated project environment:

```bat
set DJANGO_READ_ENV_FILE=true
docker compose up -d redis
python manage.py migrate
python manage.py runserver
```

Only start Redis here: your PostgreSQL development database is already installed
locally. Starting the Compose PostgreSQL service would conflict on port 5432.

Register a new test account or call the resend endpoint for an existing pending one.
In a second terminal with the same environment, process the pending mailbox:

```bat
set DJANGO_READ_ENV_FILE=true
python manage.py deliver_verification_emails
```

Open the newest file in `var/emails/`, copy its complete verification URL into your
browser and click **Verify email**. Files contain local test emails; they are ignored
by Git and are not delivered to real inboxes. If a link has expired, request another.
If a delivery previously failed, respect `next_attempt_at` or request a fresh link.
Restart the server after changing settings.

For automatic processing, run Celery worker and beat on Linux/WSL2 with the same
database/broker environment. Native Windows workers are not officially supported:

```sh
celery -A config worker --loglevel=INFO
celery -A config beat --loglevel=INFO
```

For containers, `127.0.0.1` refers to the container, so explicitly configure the
database/broker addresses for that environment. The local management command needs
no Celery worker or broker to deliver an already queued email.

## Production settings

Set a stable HTTPS `ACCOUNT_PUBLIC_BASE_URL`, real `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and TLS/SSL options through
managed environment secrets. Development deliberately uses a local file mailer even
if SMTP variables are present. Use production settings for real SMTP delivery.
Do not enable both `EMAIL_USE_TLS` and `EMAIL_USE_SSL`.

`EMAIL_VERIFICATION_TTL_SECONDS` and `EMAIL_VERIFICATION_RESEND_SECONDS` control
expiry and cooldown. Existing `.env` secrets are preserved; `.env.example` documents
the new non-secret configuration. Remember that `DJANGO_READ_ENV_FILE=true` must
be set in the shell before Django can read `.env`.

## Tests

```bat
python -m pytest apps/accounts/tests -v
python -m pytest -q
```

Fast tests use an in-memory SQLite database and mailbox. The two email-verification
concurrency tests (and two session concurrency tests) skip on SQLite; run them on a
dedicated PostgreSQL instance with a role allowed to create
test databases (never grant extra permissions to the real development role):

```bat
set TEST_DATABASE_URL=postgresql://test_user:test_password@127.0.0.1:55439/postgres
python -m pytest --ds=config.settings.postgresql_test_settings --create-db -q
```

The test database is named `test_devvault_email_verification`. Do not use a production
server. Test settings still use a memory cache and mailbox, so no real email is sent.

References: [Django signing](https://docs.djangoproject.com/en/6.0/topics/signing/),
[Django mailer configuration](https://docs.djangoproject.com/en/dev/howto/mailers-migration/),
[Celery Windows support](https://docs.celeryq.dev/en/stable/faq.html#windows).
