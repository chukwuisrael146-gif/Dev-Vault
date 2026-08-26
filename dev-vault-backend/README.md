# DevVault Backend

DevVault is a modular Django monolith for multi-tenant API access management. The current
implementation covers the architecture's Foundation step: split settings, PostgreSQL/Redis
configuration, Celery, versioned routing, operational health checks, shared model primitives,
safe structured logging, correlation IDs, a stable API error envelope, and an early custom user
model.

## Local setup

1. Copy `.env.example` to `.env` and replace every placeholder appropriate to your machine.
2. Start PostgreSQL and Redis with `docker compose up -d`.
3. Activate `venv` and install `requirements/development.txt`.
4. Run `python manage.py migrate`.
5. Run `python manage.py runserver`.

The development settings read `.env` only when `DJANGO_READ_ENV_FILE=true` is already set in the
process environment. This avoids silently loading a local file in production.

## Operational endpoints

- `GET /api/v1/health/live/` checks that the web process can serve requests.
- `GET /api/v1/health/ready/` checks the database, Redis cache, and pending migrations.

Health responses are intentionally minimal. Dependency failure details remain in redacted
application logs.

## Verification

```text
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
ruff check .
```

See `DEVVAULT_ARCHITECTURE.md` for domain ownership, security rules, and the required build order.
