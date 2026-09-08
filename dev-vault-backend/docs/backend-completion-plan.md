# Backend completion plan

Started 2026-09-08. Status: combined local MVP implemented and verified; not a
production release sign-off. Evidence is in backend-implementation-report.md.

Sources: DEVVAULT_ARCHITECTURE.md (2026-08-25), supplied Product Requirements
Document and White Paper (both 2026-08-23). Preserve the existing Accounts API and
database. Work against disposable test databases before development migrations.

## Target and scope decisions

Implement the combined frontend-ready MVP, not the documents' entire future
enterprise/distributed roadmap. Architecture owns module boundaries, `/api/v1/`
paths and error envelopes. PRD additions include both fixed-window/token-bucket
limits, signed webhooks, integration examples and asynchronous exports. Record
technical decisions and differences in ADRs; do not silently omit requirements.

No cloud deployment, external email sending, paid provider purchase, database-role
privilege changes, real webhook delivery or public release is authorized by this
local implementation task. Real production infrastructure, independent security
review, contractual SLOs and certification require separate evidence/coordination.

## Implementation checklist

- [x] Finish Accounts: profile, current user, change/reset password, recent auth,
  session revocation and decoded local email previews.
- [x] Organizations: tenant lifecycle, five roles, invitations, role changes,
  ownership transfer, last-owner protection and negative authorization tests.
- [x] Projects: canonical test/live environments, API services, archive/status
  lifecycle, tenant-aware selectors and immutable parent relationships.
- [x] Credentials: versioned HMAC pepper, random one-time keys, integration
  credentials, expiry, bounded rotation overlap, revocation, idempotency.
- [x] Access: scope catalogs/grants, versioned fixed-window/token-bucket policies,
  daily/monthly durable weighted quota reservations and adjustment ledger.
- [x] Verification: trusted integration context, strict credential separation,
  stable decisions, atomic Redis enforcement, idempotency and outage behavior.
- [x] Usage: durable sanitized events/outbox, deduplicated aggregation,
  bounded reporting/filtering, read-only reconciliation and expiring exports.
  Raw-fact retention is deliberately non-destructive pending policy approval.
- [x] Audit: tenant/actor/target evidence, safe change metadata, pagination/filtering,
  append-only controls and exports without credentials.
- [x] Webhooks: encrypted signing secrets, SSRF-safe adapter, timestamped signing,
  transactional event handoff, retry/delivery history/manual retry.
- [x] Frontend integration: OpenAPI contract, Postman collection, strict configurable
  CORS, onboarding/reference Python/Django integration and error guide.
- [x] Local operations foundations: tested dependency constraints, Docker packaging,
  local CI workflow, trust-boundary review, private metrics, alert/runbook guidance,
  backup/restore rehearsal and bounded health-timing tool. Production deployment,
  verification-load SLOs and external alert routing remain release gates below.
- [x] Verification: existing regression suite, authorization matrix, PostgreSQL
  concurrency, real Redis scripts, end-to-end flow, migration checks and reports.

## Release evidence still required outside local implementation

Independent penetration test; actual deployment TLS/secrets/least-privilege checks;
multi-AZ recovery and encrypted backup restore exercises; sustained load/latency
measurements at an agreed launch workload; real SMTP/webhook-provider checks;
retention-policy approval; alert routing and on-call ownership. Local code/tests
must not be described as satisfying these operational or organizational gates.
