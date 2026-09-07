# Accounts stage 3 implementation report

Implemented on 2026-09-07 in
`C:\Users\Israel Chukwu\Desktop\dev-vault\dev-vault-backend`.

## Result

Registration now queues a verification email durably. Added single-use, expiring
verification links, an explicit browser confirmation page, a JSON verification
endpoint, generic resend responses, per-account resend limits, IP throttling,
retryable email delivery and transactional account audit events.

Local email previews use ignored files. Production mail is configured through
environment variables. The existing private `.env`, password values, custom user
model choice and existing migration history were preserved. No packages were added.
The pre-existing change to the parent `.vscode/settings.json` was not edited.

## Files changed (13)

- `.env.example`: verification and SMTP configuration examples.
- `.gitignore`: private local mailbox and Celery scheduler files.
- `api/v1/accounts/serializers.py`: verification/resend validation and existing typo fixes.
- `api/v1/accounts/urls.py`: verification and resend routes.
- `api/v1/accounts/views.py`: endpoints and confirmation-page response headers.
- `apps/accounts/apps.py`: register configuration checks.
- `apps/accounts/exceptions.py`: safe verification/unavailable errors.
- `apps/accounts/models.py`: verification reference/durable mail record.
- `apps/accounts/services.py`: issuance, consumption, resend, retry and audit integration.
- `apps/core/logging.py`: redact verification tokens and password confirmation fields.
- `config/settings/base.py`: audit app, SMTP settings, verification settings and beat schedule.
- `config/settings/development.py`: private local file mailbox.
- `config/settings/production.py`: require explicit public origin and sender/SMTP host.

## Files created (23)

- `README.md`
- `api/v1/accounts/throttles.py`
- `apps/accounts/checks.py`
- `apps/accounts/emails.py`
- `apps/accounts/management/__init__.py`
- `apps/accounts/management/commands/__init__.py`
- `apps/accounts/management/commands/deliver_verification_emails.py`
- `apps/accounts/migrations/0003_emailverificationtoken.py`
- `apps/accounts/tasks.py`
- `apps/accounts/tests/conftest.py`
- `apps/accounts/tests/test_email_verification.py`
- `apps/accounts/tokens.py`
- `apps/audit/__init__.py`
- `apps/audit/apps.py`
- `apps/audit/migrations/__init__.py`
- `apps/audit/migrations/0001_initial.py`
- `apps/audit/models.py`
- `apps/audit/services.py`
- `config/settings/postgresql_test_settings.py`
- `docs/adr/0001-email-verification.md`
- `docs/api/email-verification.md`
- `docs/implementation-email-verification.md` (this report)
- `templates/accounts/verify_email.html`

The optional PostgreSQL settings file was initially named `test_postgresql.py`,
then renamed during verification so pytest would not mistake it for a test module.
That temporary filename is not part of the final change.

## Verification

- Baseline: 14 existing tests passed before changes.
- Final SQLite suite: 40 passed, 2 PostgreSQL-only concurrency tests skipped.
- Final PostgreSQL suite: all 42 passed, including concurrent single-use consumption
  and concurrent email delivery.
- Django system checks: no issues in test and development settings.
- Migration consistency: no model changes missing migrations.
- Ruff checks for changed/new Python code: passed.
- `git diff --check`: passed.
- Development migrations applied: `accounts.0003_emailverificationtoken` and
  `audit.0001_initial`; confirmed with `showmigrations`.
- Development PostgreSQL is reachable. Final readiness: PostgreSQL/migrations pass,
  Redis unavailable. Real Redis counter integration and real SMTP-provider delivery
  were not verified; tests use a memory cache and mailbox.

## Commands run

These commands were run from the project root using its existing virtual environment.
Some were repeated after correcting discovery/formatting issues. Initial Python and
Docker launches required execution outside the restricted sandbox.

```powershell
.\venv\Scripts\python.exe -c "import django, celery, rest_framework; print('Django', django.get_version()); print('Celery', celery.__version__); print('DRF', rest_framework.VERSION)"
.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\venv\Scripts\python.exe -B manage.py makemigrations accounts audit --settings=config.settings.test
.\venv\Scripts\python.exe -B manage.py check --settings=config.settings.test
.\venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.settings.test

$env:TEST_DATABASE_URL='postgresql://verification_test@127.0.0.1:55439/postgres'
.\venv\Scripts\python.exe -m pytest --ds=config.settings.postgresql_test_settings --create-db -q -p no:cacheprovider

.\venv\Scripts\python.exe -m ruff check --fix --no-cache api/v1/accounts/views.py
.\venv\Scripts\python.exe -m ruff format --no-cache apps/accounts/services.py apps/accounts/tokens.py apps/accounts/emails.py apps/accounts/tasks.py apps/accounts/checks.py apps/accounts/management apps/accounts/tests/test_email_verification.py apps/accounts/tests/conftest.py apps/audit api/v1/accounts config/settings/postgresql_test_settings.py
.\venv\Scripts\python.exe -m ruff check --no-cache apps/accounts/apps.py apps/accounts/models.py apps/accounts/exceptions.py apps/accounts/services.py apps/accounts/tokens.py apps/accounts/emails.py apps/accounts/tasks.py apps/accounts/checks.py apps/accounts/management apps/accounts/tests/test_email_verification.py apps/accounts/tests/conftest.py apps/audit api/v1/accounts apps/core/logging.py config/settings

$env:DJANGO_READ_ENV_FILE='true'
.\venv\Scripts\python.exe -B manage.py showmigrations accounts
.\venv\Scripts\python.exe -B manage.py migrate --plan
.\venv\Scripts\python.exe -B manage.py migrate --noinput
.\venv\Scripts\python.exe -B manage.py check
.\venv\Scripts\python.exe -B manage.py showmigrations accounts audit
.\venv\Scripts\python.exe -B manage.py shell -c "from apps.core.health import get_readiness_status; print('Readiness:', get_readiness_status())"
git diff --check
git status --short
git diff --stat
git diff --numstat
git ls-files --others --exclude-standard
```

Read-only inspection used `rg --files`, `Get-Content`, `Get-ChildItem`, `Test-Path`
and a PostgreSQL query of the current role's `rolcreatedb` flag. The role cannot
create databases; its permissions were not changed.

Docker diagnostics attempted `image ls`, `ps`, `version`, `desktop start --help`
and `desktop start --timeout 45`, using the installed executable under
`C:\Users\Israel Chukwu\AppData\Local\Programs\DockerDesktop\resources\bin`.
A hidden Docker Desktop start was also attempted. The engine stayed unavailable;
the waiting startup command was interrupted. No project containers were created.

Instead, the installed PostgreSQL 18 `initdb` created a disposable cluster under
the task workspace (`pg-email-verification-test`) with a test-only role and trust
authentication. `pg_ctl` started it bound to `127.0.0.1:55439`. The suite created
`test_devvault_email_verification` there, completely separate from development.
After testing, `pg_ctl -m fast -w stop` stopped it, the exact resolved temporary
path was checked and its generated data was removed with `Remove-Item -LiteralPath`.
No temporary test server or test data was left behind.

## Next use and build step

Open Docker Desktop and start only Redis with `docker compose up -d redis` before
using the account HTTP endpoints. PostgreSQL already runs locally on port 5432.
Process queued development emails with `python manage.py deliver_verification_emails`;
the [API guide](api/email-verification.md) explains the complete walkthrough.

Next build stage: Accounts stage 4 — login, short-lived JWT access tokens, refresh
rotation, session revocation and logout. Production SMTP credentials, automatic
worker deployment, retention jobs and database-role audit hardening remain explicit
operational setup; see the [design decision](adr/0001-email-verification.md).
