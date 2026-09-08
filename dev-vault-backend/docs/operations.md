# Operations and release runbook

This is a local MVP implementation, not a production security certification.
Do not expose Django's development server, PostgreSQL or Redis publicly.

## Configuration and secrets

The existing private `.env` is preserved. `.env.example` contains placeholders.
Production uses `config.settings.production` and requires explicit database,
Redis, broker, mail, public URL, host and independent cryptographic settings.
Run `python manage.py check --deploy` with the actual deployment configuration
before release. Do not copy the development example's HTTP/HSTS values to production.

| Configuration | Responsibility |
| --- | --- |
| DATABASE_URL | PostgreSQL application role; URL-encode password special characters |
| REDIS_URL | Security throttle and rate-counter Redis; dedicated/monitored, no eviction |
| CELERY_BROKER_URL / CELERY_RESULT_BACKEND | Worker queues/results, separate logical namespaces |
| DJANGO_SECRET_KEY | Framework signing; never rotate casually during active token workflows |
| ACCOUNT_JWT_SIGNING_KEY | Independent dashboard signing secret, at least 32 bytes |
| API_KEY_PEPPERS / API_KEY_ACTIVE_PEPPER_VERSION | Versioned independent HMAC secrets, at least 32 bytes |
| WEBHOOK_ENCRYPTION_KEYS | Ordered Fernet keys; first encrypts, old keys decrypt |
| ACCOUNT_PUBLIC_BASE_URL | Exact public HTTPS origin for account confirmation pages |
| CORS_ALLOWED_ORIGINS | Exact approved browser origins; no wildcard credentials |
| METRICS_TOKEN | Independent random 32+ character token for private metrics |
| WEBHOOK_DELIVERY_ENABLED | Explicit outbound delivery switch, false locally |

Keep peppers until every dependent API/integration credential is rotated or
revoked. Removing a version invalidates those credentials. Signing-secret rotation
is separate from encryption-at-rest rotation. Keep older Fernet keys until stored
secrets are re-encrypted; no automatic storage re-encryption command is provided.
Production secret rotation should be rehearsed and approved. Local derived keys
are convenient defaults only, never production secrets. Neither `.env`, backups
nor exported Postman credentials belong in Git.

## Containers and deployment

```sh
docker build -f docker/Dockerfile -t devvault-backend:local .
```

`compose.yaml` runs loopback-only Redis for development. Its PostgreSQL service is
behind the `database` profile; do not start it alongside the existing local server
on port 5432. The optional image is PostgreSQL 17; local verification used 18.
Never point a different PostgreSQL major version at an existing data volume.

`compose.production.yaml` separates web, worker, one beat scheduler and an explicit
migration task. It expects a separately prepared private `DEVVAULT_ENV_FILE`,
external PostgreSQL/Redis, managed SMTP and a TLS reverse proxy. It is scaffolding,
not a deployed service. Review the rendered configuration privately because
environment inspection can reveal secrets; prefer `docker compose config --quiet`.

Use a separate migration/backup role and least-privilege runtime role. Trigger
guards block ordinary updates/deletes of immutable facts, but a table owner or
superuser can disable them. Runtime roles must not own tables or run DDL. Redis
must be private, authenticated/TLS as appropriate, monitored for persistence,
replication/failover and configured without eviction of enforcement state.

Only an approved reverse proxy may set X-Forwarded-Proto; strip spoofed inbound
forwarding headers. Current application abuse throttles use REMOTE_ADDR, so a
proxy deployment must also enforce client-aware edge throttling. Set request size,
connection, concurrency and timeout limits at the edge. Do not log raw URLs/query
strings, bodies or authorization headers there. Serve collected admin static assets
through the deployment's static server; the API itself returns JSON.

## Background work

Start a Celery worker and exactly one beat scheduler. Durable database records,
not transient queue messages alone, hold pending mail, usage aggregation, exports
and webhook deliveries. Workers poll them periodically. Development manual commands:

```sh
python manage.py deliver_account_emails
python manage.py deliver_invitations
python manage.py aggregate_usage
python manage.py reconcile_usage
python manage.py cleanup_exports
```

`reconcile_usage` uses a read-only consistent snapshot, compares each quota bucket
with reservation/adjustment ledgers and checks global aggregated request/unit
totals against receipted events. It reports pending aggregation separately and
never resets customer counters. This is not a per-dimension historical checksum.
Investigate drift offline before a reviewed repair. `cleanup_exports --apply`
deletes only expired generated CSVs and marks jobs expired; source facts remain.
Without `--apply` it is a dry run. Schedule bounded passes after approving retention.

Raw usage, audit, idempotency and delivery history are retained by default; there
is deliberately no broad destructive pruning task. Approve privacy/retention,
archive and partition plans before production volume. Export downloads expire
after 24 hours even before physical cleanup. Monitor disk usage and pending jobs.

## Webhooks

Delivery is off until explicitly enabled. Endpoints must use public HTTPS port
443; private/reserved addresses, credentials/query/fragment, redirects and unsafe
DNS answers are refused. DNS is checked and connection IP pinned; TLS still verifies
the original hostname. Apply network egress restrictions as an additional layer.
Payloads contain sanitized event metadata, not API keys or passwords. Receivers
must verify the timestamped HMAC against the **raw body**, reject stale signatures,
and deduplicate event IDs. Delivery is at least once. See the signing implementation
in `apps/webhooks/crypto.py` and the API for signing-key versions/delivery history.

Automatic attempts are bounded (8); permanent errors enter dead letter. Review
the failure code/destination before a recent-authenticated manual retry. Signing
secret rotation takes effect for subsequent attempts, including queued events.
Real outbound webhook/SMTP tests were not performed during local implementation.

## Health, metrics and alert checklist

- `/api/v1/health/live/`: process liveness, no dependency queries.
- `/api/v1/health/ready/`: database, Redis and unapplied migrations; fail readiness
  rather than routing verification traffic to an unhealthy instance.
- `/internal/metrics/`: hidden unless a strong METRICS_TOKEN is configured; scrape
  with its Bearer token over a private network. Request totals and duration labels
  use route templates, not user IDs or raw paths. Gunicorn uses Prometheus
  multiprocess storage when configured; start with a fresh dedicated directory.
- Alert on sustained readiness failure, verification 5xx/latency, abnormal 401/429,
  Redis errors/evictions, PostgreSQL contention, queue backlog/oldest pending jobs,
  dead-letter deliveries, reconciliation drift and export/backup disk capacity.

The repository does not configure an external alert receiver or on-call rotation.
Set thresholds against an agreed workload; do not claim latency/availability SLOs
from unit tests. `python scripts/load_smoke.py` runs bounded loopback liveness
timings only. Launch load tests must cover real verification, mixed tenants,
policy dimensions, key rotation, quotas, dependency failures and recovery.

## Backup, restore and migration safety

```sh
python manage.py backup_database
```

This writes a custom-format private dump under ignored `var/backups/`, without a
password in command arguments. Keep production backups encrypted and off-host;
match pg_dump to server version and separately configure verified TLS/PG service
settings where needed. Treat the local dump as private database data, not a report.

Rehearse an existing project-local dump from PowerShell:

```powershell
./scripts/test_postgresql.ps1 -BackupFile ./var/backups/<exact-backup-name>.dump
```

The script restores into a disposable loopback cluster, applies migrations there,
runs checks/tests, stops it, then removes only that cluster after success. A failure
retains the stopped cluster for inspection; it can contain private restored data.
Do not restore over development or production without a separate recovery decision.
Before real upgrades: take/verify a backup, review `migrate --plan`, rehearse against
a restored copy, apply migrations once with the migration role and check readiness.

## Trust boundaries and known trade-offs

- Dashboard JWTs, consumer API keys and server integration credentials are separate.
  Tenant selectors, capability checks and immutable parent relationships prevent
  ordinary cross-tenant access. UUIDs alone are not access control.
- A compromised trusted integration credential can submit dishonest cost/scope
  context; customers must secure their backend and still authorize their own records.
- All applicable policies constrain verification. PostgreSQL commits quota, usage
  and idempotency facts atomically. Redis consumption can precede a later failed
  database commit, conservatively reducing rate capacity; this never returns an
  allowance without durable usage. There is no cross-database distributed transaction.
- Redis persistence loss can lose short-lived rate counters; durable quotas remain
  in PostgreSQL. Production failover/persistence policy must match the promised SLO.
- Mutable aggregates are projections; audit/usage/adjustment/revision facts have
  PostgreSQL trigger guards. This is not protection against a privileged DBA.
- Current synchronous transaction locks favor correctness over very-high-throughput
  scaling. No multi-region enforcement or horizontal scaling SLO was proven.

## Gates still required before a public launch

Independent penetration test; production TLS/secret/role review; encrypted remote
backup recovery and agreed RPO/RTO; sustained verification load and failure tests;
real SMTP and controlled webhook receiver tests; retention approval; monitored
worker/queue deployment; alert routing and an on-call owner. CI was added locally,
not pushed or executed in GitHub. No public deployment or security certification
has been made as part of this implementation.
