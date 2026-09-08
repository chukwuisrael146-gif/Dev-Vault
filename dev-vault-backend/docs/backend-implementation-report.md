# Backend implementation report

Verified 2026-09-08. Project: `C:\Users\Israel Chukwu\Desktop\dev-vault\dev-vault-backend`.

## Outcome and scope

The combined frontend-ready MVP is implemented in the existing modular Django
monolith, extending the previously working Foundation/Accounts code. This is a
local implementation and validation handover, not a claim that every V2/V3 idea
or a public production release is complete.

Sources reviewed: the preserved DEVVAULT_ARCHITECTURE.md (2026-08-25), supplied
DevVault Product Requirements Document and White Paper (2026-08-23). The document
reading workflow was used to inspect the Word sources without changing them.
Architecture owns module boundaries, versioned delivery and security primitives;
the PRD adds token-bucket enforcement, signed webhooks, exports and reference
integration. ADRs 0003/0004 record scope and consistency choices.

| Requirement group | Implementation |
| --- | --- |
| Accounts | Profile, password change/reset, recent authentication and session revocation, extending existing registration/verification/login/refresh/logout |
| Teams and tenancy | Organizations, five membership roles, invitations, ownership transfer and last-owner protection |
| Resource hierarchy | Projects, canonical test/live environments and service lifecycle, scoped selectors and PostgreSQL identity guards |
| Credentials | One-time high-entropy keys/integration credentials, versioned HMAC verifiers, expiration/revocation and bounded rotation overlap |
| Permissions and policies | Service scopes, grants, immutable policy revisions, all-applicable most-restrictive evaluation |
| Verification | Separate trusted service proof plus consumer key, strict context/input, fail-closed Redis and PostgreSQL behavior, idempotent weighted quota reservations |
| Usage | Durable sanitized events, receipt-deduplicated hourly aggregates, hourly/daily exact-range reports, read-only ledger reconciliation and expiring CSV exports |
| Audit | Tenant/actor/action evidence, authorization-denial capture, safe metadata, append-only PostgreSQL triggers and authorized CSV exports |
| Webhooks | Encrypted signing secrets, timestamped HMAC, transactional outbox, SSRF-safe HTTPS adapter, bounded retries and history; actual outbound delivery remains disabled |
| Frontend | Complete generated OpenAPI, interactive docs, secret-free Postman starter, exact-origin CORS and local Python/Django SDK |
| Local operations | Dependency constraints, non-root Linux image, web/worker/beat Compose scaffolding, private metrics, backup/restore tooling, CI workflow and runbook |

No incompatible user-model replacement, empty diagram-only folders, cloud
deployment, external real email/webhook delivery, purchases, commits or pushes
were performed. Billing, SSO/SCIM, multi-region enforcement, automated anomaly
response, advanced notification/rotation workflows and formal compliance remain
outside this delivery. Raw-fact deletion/archival requires retention approval;
only generated export artifacts have an explicit cleanup command.

## Verification evidence

| Gate | Observed result |
| --- | --- |
| Full PostgreSQL 18 + Redis 7.4 suite | **201 passed**, no skips/warnings, 31.32 seconds |
| Fast SQLite suite | **189 passed, 12 integration-only skips**, no warnings |
| Fast suite statement/branch coverage | **84.11%**, existing 80% minimum preserved |
| Ruff lint and format | Passed; 193 Python files formatted/checked |
| Django checks and migration drift | No issues; no model changes missing migrations; development migrations fully applied |
| OpenAPI validation | Passed with fail-on-warn, generated contract refreshed |
| Installed-environment dependency audit | No known vulnerabilities found after upgrading cryptography to 50.0.1 |
| Static security scan | No medium/high findings; 6 low findings reviewed (Bearer/token-prefix constants and intentional argument-list subprocess backup invocation) |
| Git-visible secret scan | No recognizable real credentials/private keys found; not a substitute for independent review |
| Python SDK compatibility | SDK tests passed; Python 3.11 syntax validated (runtime tests used Python 3.14) |
| Linux packaging | Image built successfully; Gunicorn startup issue found by smoke test, fixed and regression-tested |
| Container health smoke | 50 requests, 0 failures; local liveness only, not a verification/production SLO benchmark |
| Production settings / Compose | Synthetic production configuration had no errors; HSTS preload warning deliberately retained; Compose syntax validated without exposing env values |
| Backup recovery rehearsal | Private local dump restored into disposable PostgreSQL, upgraded and checked successfully before the real upgrade |
| Actual development readiness | HTTP 200 with PostgreSQL, Redis and migration checks |

Concurrency tests cover duplicate operation IDs and shared quota contention.
Real Redis tests cover concurrent fixed-window budgets, token-bucket behavior,
multi-policy no-partial-consumption and the complete verification/replay/denial/
reporting/revocation path. Other tests cover tenant boundaries, role restrictions,
one-time secrets, credential rotation, expired/reused account tokens, durable
outbox failure, SSRF/signatures/retries, CSV escaping and SQL immutability guards.

The initial dependency audit found vulnerable cryptography 48.0.1; the installed
environment and constraints were upgraded to 50.0.1 and the audit rerun successfully.
The initial Linux smoke test exposed Gunicorn's shallow logging-config merge;
explicit safe/error and discarded raw-access loggers fixed the startup failure.

## Existing data and runtime state

Your private `.env` was not edited. The pre-existing unrelated parent
`.vscode/settings.json` change was left untouched. The source documents were not
changed. All **5 existing users and 13 audit records** remained after migration.

A pre-upgrade private backup is retained at:

`var/backups/devvault-0f5197f629c640d09f224caeb4cf629b.dump`

It contains private database data and is ignored by Git. It is not encrypted
off-host production backup infrastructure. Keep it private.

18 additive/new-domain migrations were applied after rehearsal, including
PostgreSQL immutable-fact and identity triggers. No application role was granted
CREATEDB and no user tables were recreated. Test clusters were stopped and removed
after successful runs; temporary smoke containers were removed. Redis remains
healthy with its existing volume, now bound only to `127.0.0.1:6379`.
The local `devvault-backend:local` image remains available. No web server, worker or
beat process was left running by this turn; restart your development server to
load the new code. Existing independently started processes were not stopped.

Ignored runtime artifacts (venv package updates, coverage/cache files and the
private backup) are not included in the source-file manifest below.

## Commands run

Principal build/verification invocations are listed below; repeated invocations
and read-only file/search diagnostics are condensed. Python refers to the
project's `venv\Scripts\python.exe`. Docker was invoked by its installed absolute
path because it was not in this session's PATH. Environment values were not printed.

```powershell
python -m pip install 'cryptography>=50,<51'
python -m pip install prometheus-client pip-audit bandit
python -m pip check
python -m pip_audit --local --strict --progress-spinner off
python -m ruff check --fix .
python -m ruff format .
python -m ruff check --no-cache .
python -m ruff format --check .
python -m pytest -q --cov --cov-report=term -p no:cacheprovider
./scripts/test_postgresql.ps1
./scripts/test_postgresql.ps1 -BackupFile ./var/backups/devvault-0f5197f629c640d09f224caeb4cf629b.dump
python manage.py check
python manage.py showmigrations --plan
python manage.py makemigrations --check --dry-run
python manage.py backup_database
python manage.py migrate --noinput
python manage.py migrate --check
python manage.py reconcile_usage
python manage.py spectacular --settings=config.settings.test --file docs/openapi.yaml --validate --fail-on-warn
python scripts/generate_postman.py
python scripts/check_secrets.py
docker compose config --quiet
docker compose up -d redis
docker compose ps --format json
docker build -f docker/Dockerfile -t devvault-backend:local .
python scripts/load_smoke.py --base-url http://127.0.0.1:18081
docker compose -f compose.production.yaml config --quiet
git diff --check
```

Dependency installation also added the API-schema/CORS libraries and their
dependencies. Django makemigrations generated the new-domain migrations; reviewed
PostgreSQL guard migrations were added explicitly. Bandit was invoked with
`-r apps api integrations/python/devvault_sdk`, test directories excluded, and
`-ll` (medium/high gate). Temporary Docker runs used synthetic settings and a
loopback port; their exact named containers were stopped/removed. Production
`check --deploy` ran inside the image with process-local synthetic secrets and
no external delivery. A Django shell invoked the real migrate command together
with before/after counts, reconciliation and a readiness request. The SDK syntax
check used Python's AST parser with `feature_version=(3,11)`.

## Frontend handover and public-release gates

Start using [the frontend guide](frontend-integration.md), [OpenAPI](openapi.yaml),
[Postman collection](devvault.postman_collection.json) and [README](../README.md).
Set only your intended local frontend origin in the existing private environment
when the frontend is created. Begin with account and organization/project screens,
then key management, policy editing and usage/audit.

Before a public launch: independent security review/penetration test; deployment
TLS and least-privilege roles; managed secrets/rotation rehearsal; real SMTP and
approved webhook receiver checks; sustained verification load/failure testing;
encrypted remote backup recovery/RPO/RTO; raw-history retention approval; worker
monitoring, alert routing and on-call ownership. See [operations](operations.md).
Local tests do not prove those operational or organizational requirements. The
GitHub Actions workflow is created locally but has not been pushed or run remotely.
Dependency constraints record tested versions, not a hash-locked supply-chain
attestation or immutable base-image pin.

## Exact source-file manifest

156 created and 22 changed files.
Paths are relative to the backend folder; `../.github/` is the repository-level
workflow. The unrelated pre-existing editor setting is excluded.

| Action | File |
| --- | --- |
| Changed | `.env.example` |
| Changed | `README.md` |
| Changed | `api/v1/accounts/urls.py` |
| Changed | `api/v1/urls.py` |
| Changed | `apps/accounts/admin.py` |
| Changed | `apps/accounts/checks.py` |
| Changed | `apps/accounts/models.py` |
| Changed | `apps/accounts/tasks.py` |
| Changed | `apps/accounts/tests/test_models.py` |
| Changed | `apps/audit/models.py` |
| Changed | `apps/audit/services.py` |
| Changed | `apps/core/context.py` |
| Changed | `apps/core/exceptions.py` |
| Changed | `apps/core/logging.py` |
| Changed | `apps/core/middleware.py` |
| Changed | `apps/core/models.py` |
| Changed | `compose.yaml` |
| Changed | `config/settings/base.py` |
| Changed | `config/settings/production.py` |
| Changed | `config/urls.py` |
| Changed | `pyproject.toml` |
| Changed | `requirements/base.txt` |
| Created | `../.github/workflows/backend.yml` |
| Created | `.dockerignore` |
| Created | `api/v1/access/__init__.py` |
| Created | `api/v1/access/serializers.py` |
| Created | `api/v1/access/urls.py` |
| Created | `api/v1/access/verification.py` |
| Created | `api/v1/access/views.py` |
| Created | `api/v1/accounts/profile.py` |
| Created | `api/v1/credentials/__init__.py` |
| Created | `api/v1/credentials/serializers.py` |
| Created | `api/v1/credentials/urls.py` |
| Created | `api/v1/credentials/views.py` |
| Created | `api/v1/exceptions.py` |
| Created | `api/v1/helpers.py` |
| Created | `api/v1/organizations/__init__.py` |
| Created | `api/v1/organizations/serializers.py` |
| Created | `api/v1/organizations/urls.py` |
| Created | `api/v1/organizations/views.py` |
| Created | `api/v1/projects/__init__.py` |
| Created | `api/v1/projects/serializers.py` |
| Created | `api/v1/projects/urls.py` |
| Created | `api/v1/projects/views.py` |
| Created | `api/v1/reporting.py` |
| Created | `api/v1/schema.py` |
| Created | `api/v1/webhooks.py` |
| Created | `apps/access/__init__.py` |
| Created | `apps/access/apps.py` |
| Created | `apps/access/migrations/0001_initial.py` |
| Created | `apps/access/migrations/0002_quotanotice.py` |
| Created | `apps/access/migrations/0003_fact_identity_guards.py` |
| Created | `apps/access/migrations/__init__.py` |
| Created | `apps/access/models.py` |
| Created | `apps/access/quotas.py` |
| Created | `apps/access/rate_limits.py` |
| Created | `apps/access/selectors.py` |
| Created | `apps/access/services.py` |
| Created | `apps/access/tests/__init__.py` |
| Created | `apps/access/tests/conftest.py` |
| Created | `apps/access/tests/test_access.py` |
| Created | `apps/access/tests/test_postgresql_concurrency.py` |
| Created | `apps/access/tests/test_real_redis.py` |
| Created | `apps/access/tests/test_real_verification.py` |
| Created | `apps/access/verification.py` |
| Created | `apps/accounts/management/commands/deliver_account_emails.py` |
| Created | `apps/accounts/management/commands/preview_email.py` |
| Created | `apps/accounts/migrations/0005_passwordresetrequest.py` |
| Created | `apps/accounts/profile_services.py` |
| Created | `apps/accounts/tests/test_profile_passwords.py` |
| Created | `apps/audit/migrations/0003_auditlog_changes_auditlog_organization_id.py` |
| Created | `apps/audit/migrations/0004_auditexport_auditlog_actor_type_auditlog_source_ip.py` |
| Created | `apps/audit/migrations/0005_append_only_guard.py` |
| Created | `apps/audit/selectors.py` |
| Created | `apps/audit/tasks.py` |
| Created | `apps/core/dbguards.py` |
| Created | `apps/core/exports.py` |
| Created | `apps/core/idempotency.py` |
| Created | `apps/core/management/__init__.py` |
| Created | `apps/core/management/commands/__init__.py` |
| Created | `apps/core/management/commands/backup_database.py` |
| Created | `apps/core/management/commands/cleanup_exports.py` |
| Created | `apps/core/metrics.py` |
| Created | `apps/core/migrations/0001_initial.py` |
| Created | `apps/core/migrations/__init__.py` |
| Created | `apps/core/parsers.py` |
| Created | `apps/core/tests/test_api_contract.py` |
| Created | `apps/core/tests/test_database_guards.py` |
| Created | `apps/core/tests/test_operations.py` |
| Created | `apps/credentials/__init__.py` |
| Created | `apps/credentials/apps.py` |
| Created | `apps/credentials/checks.py` |
| Created | `apps/credentials/hashing.py` |
| Created | `apps/credentials/migrations/0001_initial.py` |
| Created | `apps/credentials/migrations/0002_apikey_family_id.py` |
| Created | `apps/credentials/migrations/__init__.py` |
| Created | `apps/credentials/models.py` |
| Created | `apps/credentials/selectors.py` |
| Created | `apps/credentials/services.py` |
| Created | `apps/credentials/tests/__init__.py` |
| Created | `apps/credentials/tests/test_credentials.py` |
| Created | `apps/organizations/__init__.py` |
| Created | `apps/organizations/apps.py` |
| Created | `apps/organizations/management/__init__.py` |
| Created | `apps/organizations/management/commands/__init__.py` |
| Created | `apps/organizations/management/commands/deliver_invitations.py` |
| Created | `apps/organizations/migrations/0001_initial.py` |
| Created | `apps/organizations/migrations/__init__.py` |
| Created | `apps/organizations/models.py` |
| Created | `apps/organizations/permissions.py` |
| Created | `apps/organizations/selectors.py` |
| Created | `apps/organizations/services.py` |
| Created | `apps/organizations/tasks.py` |
| Created | `apps/organizations/tests/__init__.py` |
| Created | `apps/organizations/tests/test_organizations.py` |
| Created | `apps/projects/__init__.py` |
| Created | `apps/projects/apps.py` |
| Created | `apps/projects/migrations/0001_initial.py` |
| Created | `apps/projects/migrations/0002_identity_guards.py` |
| Created | `apps/projects/migrations/__init__.py` |
| Created | `apps/projects/models.py` |
| Created | `apps/projects/selectors.py` |
| Created | `apps/projects/services.py` |
| Created | `apps/projects/tests/__init__.py` |
| Created | `apps/projects/tests/test_projects.py` |
| Created | `apps/usage/__init__.py` |
| Created | `apps/usage/apps.py` |
| Created | `apps/usage/exports.py` |
| Created | `apps/usage/management/__init__.py` |
| Created | `apps/usage/management/commands/__init__.py` |
| Created | `apps/usage/management/commands/aggregate_usage.py` |
| Created | `apps/usage/management/commands/reconcile_usage.py` |
| Created | `apps/usage/migrations/0001_initial.py` |
| Created | `apps/usage/migrations/0002_usageexport.py` |
| Created | `apps/usage/migrations/0003_fact_guards.py` |
| Created | `apps/usage/migrations/__init__.py` |
| Created | `apps/usage/models.py` |
| Created | `apps/usage/selectors.py` |
| Created | `apps/usage/services.py` |
| Created | `apps/usage/tasks.py` |
| Created | `apps/usage/tests/__init__.py` |
| Created | `apps/usage/tests/test_reporting.py` |
| Created | `apps/webhooks/__init__.py` |
| Created | `apps/webhooks/apps.py` |
| Created | `apps/webhooks/checks.py` |
| Created | `apps/webhooks/crypto.py` |
| Created | `apps/webhooks/migrations/0001_initial.py` |
| Created | `apps/webhooks/migrations/0002_attempt_guard.py` |
| Created | `apps/webhooks/migrations/__init__.py` |
| Created | `apps/webhooks/models.py` |
| Created | `apps/webhooks/receivers.py` |
| Created | `apps/webhooks/services.py` |
| Created | `apps/webhooks/tasks.py` |
| Created | `apps/webhooks/tests/__init__.py` |
| Created | `apps/webhooks/tests/test_webhooks.py` |
| Created | `apps/webhooks/transport.py` |
| Created | `compose.production.yaml` |
| Created | `docker/Dockerfile` |
| Created | `docker/gunicorn.conf.py` |
| Created | `docs/adr/0003-combined-mvp-scope.md` |
| Created | `docs/adr/0004-enforcement-consistency.md` |
| Created | `docs/backend-completion-plan.md` |
| Created | `docs/devvault.postman_collection.json` |
| Created | `docs/frontend-integration.md` |
| Created | `docs/openapi.yaml` |
| Created | `docs/operations.md` |
| Created | `integrations/python/README.md` |
| Created | `integrations/python/devvault_sdk/__init__.py` |
| Created | `integrations/python/devvault_sdk/django.py` |
| Created | `integrations/python/pyproject.toml` |
| Created | `integrations/python/tests/test_client.py` |
| Created | `requirements/constraints.txt` |
| Created | `scripts/check_secrets.py` |
| Created | `scripts/generate_postman.py` |
| Created | `scripts/load_smoke.py` |
| Created | `scripts/test_postgresql.ps1` |
| Created | `templates/accounts/reset_password.html` |
| Created | `docs/backend-implementation-report.md` |

