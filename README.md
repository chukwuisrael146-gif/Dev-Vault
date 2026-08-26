# DevVault Backend

DevVault is a multi-tenant API access-management platform built as a modular Django monolith. It
will let developers and organizations manage projects, environments, API services, credentials,
permissions, rate limits, quotas, usage, and audit history.

The repository currently implements the **Foundation** phase. The next build phase is
**Accounts**.

## Current implementation

- Django settings split into base, development, production, and test environments.
- Environment-driven PostgreSQL configuration using `django-environ` and `psycopg`.
- Redis cache configuration and Celery broker/result integration.
- Versioned `/api/v1/` delivery layer.
- Liveness and dependency-aware readiness endpoints.
- Shared UUID primary-key and UTC timestamp model primitives.
- Request/correlation IDs propagated through responses and structured logs.
- JSON logging with allowlisted fields and secret redaction.
- Consistent DRF error envelope.
- Email-only custom user model created before the first project migration.
- Pytest, Ruff, and migration-drift checks.

Authentication endpoints and the remaining business domains are not implemented yet.

## Technology stack

- Python 3.14
- Django 6.1
- Django REST Framework
- PostgreSQL
- Redis
- Celery
- Pytest and pytest-django
- Ruff

## Project structure

```text
dev-vault-backend/
|-- manage.py
|-- pyproject.toml
|-- .env.example
|-- compose.yaml
|-- DEVVAULT_ARCHITECTURE.md
|-- requirements/
|   |-- base.txt
|   |-- development.txt
|   `-- production.txt
|-- config/
|   |-- celery.py
|   |-- urls.py
|   |-- asgi.py
|   |-- wsgi.py
|   `-- settings/
|       |-- base.py
|       |-- development.py
|       |-- production.py
|       `-- test.py
|-- apps/
|   |-- core/
|   `-- accounts/
`-- api/
    |-- urls.py
    `-- v1/
        `-- urls.py
```

Future domain folders will be added only when their implementation begins. Empty folders are not
created merely to reproduce the architecture diagram.

## Local development setup

The commands below use Windows PowerShell from the repository root.

### 1. Create and activate a virtual environment

Skip creation if `venv` already exists.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements\development.txt
```

### 2. Create local environment configuration

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace its placeholders. At minimum, configure a private Django secret key and
your database connection:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings.development
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=replace-with-a-long-random-value
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://devvault:URL_ENCODED_PASSWORD@127.0.0.1:5432/devvault
```

Passwords containing URL-reserved characters must be encoded in `DATABASE_URL`; for example,
`@` becomes `%40` and `#` becomes `%23`. Never commit `.env` or share its contents.

The settings intentionally load `.env` only when explicitly enabled. Enable it in every new
PowerShell session used to run Django:

```powershell
$env:DJANGO_READ_ENV_FILE = "true"
```

### 3. Start infrastructure

Choose one PostgreSQL approach; do not run two PostgreSQL servers on port `5432`.

#### Existing local PostgreSQL/pgAdmin

Create or use the following database and login role, then place the role's private password in
`DATABASE_URL`:

```text
Host: 127.0.0.1
Port: 5432
Database: devvault
Username: devvault
```

pgAdmin manages the connection; the PostgreSQL Windows service must be running.

#### Docker Compose

If Docker is installed and port `5432` is free:

```powershell
docker compose up -d postgres redis
```

If local PostgreSQL is already running and only Redis is needed:

```powershell
docker compose up -d redis
```

Redis defaults to `127.0.0.1:6379`. It is required for a successful readiness check and later
Celery processing, but it is not required to run database migrations.

### 4. Apply migrations

Preview the plan, then create the database tables:

```powershell
.\venv\Scripts\python.exe manage.py migrate --plan
.\venv\Scripts\python.exe manage.py migrate
```

### 5. Create a local administrator

```powershell
.\venv\Scripts\python.exe manage.py createsuperuser
```

The custom user model signs in with an email address rather than a username.

### 6. Run the application

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

Useful local URLs:

- Admin: `http://127.0.0.1:8000/admin/`
- Liveness: `http://127.0.0.1:8000/api/v1/health/live/`
- Readiness: `http://127.0.0.1:8000/api/v1/health/ready/`

## Health behavior

`GET /api/v1/health/live/` confirms that the Django process can serve a request:

```json
{"status": "ok"}
```

`GET /api/v1/health/ready/` verifies PostgreSQL, Redis, and migration state. It returns HTTP `503`
with `{"status":"not_ready"}` if a required dependency is unavailable. Public responses do not
reveal which dependency failed; that information is written to redacted structured logs.

## API error format

DRF errors use a stable envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request contains invalid data.",
    "details": {},
    "request_id": "correlation-id"
  }
}
```

Error codes are intended for application logic. Messages are human-readable, and `request_id`
connects a response to safe application logs.

## Development checks

Run these before committing changes:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe -m ruff check .
.\venv\Scripts\python.exe -m ruff format --check .
.\venv\Scripts\python.exe -m pip check
```

Tests use an isolated in-memory SQLite database. Development and production use PostgreSQL.

## Settings modules

| Module | Purpose |
|---|---|
| `config.settings.development` | Local development with PostgreSQL and optional browsable API |
| `config.settings.test` | Isolated automated tests with in-memory SQLite and local-memory cache |
| `config.settings.production` | Strict environment-only secrets and production security controls |

Production refuses to start unless its database, Redis, Celery, host, and secret-key environment
variables are explicitly provided.

## Security notes

- Never commit `.env`, passwords, API keys, JWTs, cookies, or authorization headers.
- Do not use the PostgreSQL `postgres` administrator role as the Django application user.
- Use separate credentials and data stores for development, staging, and production.
- Raw DevVault API keys must never be stored or logged when credential development begins.
- Treat test and live environments as separate security domains.

## Roadmap

The authoritative build order is:

1. Foundation — complete.
2. Accounts — next: registration, email verification, JWT sessions, logout, and password reset.
3. Organizations and tenant-isolation controls.
4. Projects, test/live environments, and API services.
5. Secure credential issuance, rotation, expiry, and revocation.
6. Permissions, rate limits, quotas, and access verification.
7. Usage metering and aggregation.
8. Immutable audit history.
9. Operational hardening and public integration documentation.

See `DEVVAULT_ARCHITECTURE.md` for domain ownership, security requirements, architecture
guardrails, and the complete delivery plan.
