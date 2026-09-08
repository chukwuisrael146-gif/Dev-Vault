# ADR 0004 Enforcement, retries and metering

Accepted for the frontend-ready MVP.

## Trust boundary

Dashboard access JWTs authenticate people. `dv_test_*` / `dv_live_*` authenticate
consumers to one API service. `dvs_*` authenticates the service's private backend
to DevVault. Verification requires both consumer and integration credentials.
Only that trusted backend chooses required scopes, audience, HTTP method and
weighted units. DevVault does not authorize ownership of the customer's records.

## Policy behavior

All applicable active policies constrain the request: organization/environment
kind, project, service and optional key family. This deliberately uses the PRD's
most-restrictive rule, rather than replacing broader limits with a key override.
The typed `Policy` table stores fixed-window, token-bucket, daily and monthly
variants, with immutable targets and immutable `PolicyRevision` snapshots.
Dimensions are shared policy budget or key family; arbitrary labels are not
accepted. Configuration is read from PostgreSQL for each decision, not a stale
authorization cache. There is a 64-active-policy-per-organization/environment cap.

Rate requests cost one token; quota requests consume the supplied positive
weighted units. Quotas count authorized attempts, not customer business success.
Daily/monthly boundaries are UTC. There is no financial settlement/refund claim.

## Atomicity and retries

Redis evaluates all short-window limits before consuming any. PostgreSQL locks
the key, policies and quota buckets in a fixed order. Quota increments, immutable
reservations, the sanitized decision event and its idempotency record commit
together before an allow response. An unavailable database/Redis cannot permit
access. A failed SQL commit after Redis consumption can conservatively use rate
capacity, but cannot return allow or commit quota without its event.

`Idempotency-Key` is mandatory for verification. Exact retries replay a durable
decision without spending quota again, after checking current key validity and
scope grants. Different input with the same ID is a conflict. The customer backend
must own these IDs and deduplicate its own business operation/results. A replayed
DevVault reservation is **not** permission to execute a new business operation.
The reference Django decorator generates a new server-owned ID per incoming
request and does not automatically retry.

Rotation preserves `family_id`, grants and key-family policies. Rotation does not
reset quota or rate counters. Key overlap is explicit, bounded to 24 hours, and
never extends original expiry. Policy edits retain quota bucket identity/usage;
rate policy revisions intentionally start new short-window counters and are
audited. Allowance credits/debits are separate immutable adjustments.

Revocation is checked on every request. In-flight work that already passed its
authorization decision is not cancelled retroactively. Parent archive/disable
blocks subsequent decisions. This is not a distributed transaction with the
customer's application and does not promise exactly-once business execution.

## Events and webhooks

Usage events are authoritative; aggregation receipts make reprocessing idempotent.
Reports currently query bounded event ranges for exact totals; aggregates are
available for future high-volume reporting optimization. Webhook rows are queued
in the mutation/decision transaction. Delivery is at least once: receivers must
deduplicate event IDs. Receivers verify HMAC over `timestamp.raw_body`, allow a
small clock tolerance (for example five minutes), and compare signatures in
constant time. Signing-secret rotation takes effect immediately, including queued
deliveries; delivery attempts record the version in their request header.

PostgreSQL triggers reject audit/usage/history updates and deletion and immutable
parent changes. This protects the application path, not against a database owner
who can drop triggers. Production separates migration and application roles.

Retention of authoritative events is deliberately non-destructive by default.
Exports expire for download after 24 hours; operational deletion/archival must
follow an approved policy. No silent truncation, quota reset or automatic deletion
of account/security history is enabled.
