# DevVault Backend Architecture

**Document type:** Backend architecture source of truth  
**Status:** Proposed baseline for implementation  
**Primary audience:** Backend engineers, platform engineers, security reviewers, technical product managers, and contributors  
**Last updated:** 2026-08-25

---

## 1. Purpose of This Document

This document defines the recommended backend architecture for DevVault. It establishes domain boundaries, infrastructure responsibilities, security rules, implementation conventions, delivery phases, and the intended evolution of the platform.

All backend implementation work should follow this document unless an Architecture Decision Record (ADR) explicitly changes a decision. When code and this document disagree, the discrepancy should be resolved before new functionality is built on top of it.

## 2. Project Overview and Product Definition

DevVault is a multi-tenant API access-management platform. It enables developers and organizations to create projects, define API services and environments, issue and revoke API keys, enforce permissions, rate limits, and quotas, and inspect usage and audit history.

DevVault has two distinct responsibilities:

1. **Management:** Provide authenticated users with a control plane for organizations, projects, environments, services, credentials, policies, usage views, and audit records.
2. **Enforcement:** Provide a low-latency access engine that verifies API-consumer credentials and evaluates authorization, rate-limit, and quota policies for protected APIs.

DevVault is not the customer's business API. It is the trust and policy layer used to control access to that API.

### 2.1 Core product flow

```text
Developer Account
        |
        v
Organization + Membership
        |
        v
Project
        |
        v
Environment
        |
        v
API Service
        |
        v
API Key + Policies
        |
        v
Credential Verification
        |
        +--> Authentication
        +--> Scope/Permission Evaluation
        +--> Rate-Limit Evaluation
        +--> Quota Evaluation
        |
        v
Decision + Usage Event + Audit Trail
```

### 2.2 Product goals

- Make secure API-key issuance and verification easy to integrate.
- Centralize access rules without coupling DevVault to customer business logic.
- Provide strong tenant and environment isolation.
- Support low-latency policy evaluation and reliable usage metering.
- Give operators a defensible audit history.
- Establish a foundation for usage-based billing, entitlements, SDKs, and enterprise controls.

## 3. Architectural Principles

| Principle | Application |
|---|---|
| Secure by default | Raw API keys are shown once, never stored or logged, and all access is deny-by-default. |
| Explicit domain ownership | Each Django app owns a bounded domain and cannot reach into another app's persistence internals. |
| Tenant isolation everywhere | Every tenant-owned resource is scoped through its organization, including queries, cache keys, jobs, events, and metrics. |
| Environment isolation | Test and live credentials, policies, counters, and usage cannot cross environments. |
| Thin delivery layer | Views handle HTTP; serializers validate transport data; services execute use cases; selectors read data. |
| Transactional correctness | Security and lifecycle mutations use database transactions, constraints, and explicit locking where needed. |
| Fast path/slow path separation | Synchronous verification is kept minimal; aggregation, notifications, and exports run asynchronously. |
| Least privilege | Users, services, keys, workers, and infrastructure identities receive only required permissions. |
| Observable decisions | Security-relevant actions and verification outcomes are measurable and traceable without exposing secrets. |
| Evolution over premature distribution | Start with a modular monolith, preserving boundaries that allow later extraction of high-scale services. |
| Versioned contracts | Public APIs, event schemas, and SDK behavior evolve through explicit versions. |
| Idempotency where retries occur | Mutating public operations and background jobs must tolerate safe retry where applicable. |

## 4. Recommended Backend Stack

| Concern | Technology | Responsibility |
|---|---|---|
| Language | Python | Application and worker implementation |
| Web framework | Django | Domain models, migrations, administration, settings, and request lifecycle |
| API framework | Django REST Framework (DRF) | Versioned HTTP APIs, serializers, authentication, permissions, throttling integration, and response conventions |
| Primary datastore | PostgreSQL | Source of truth for tenants, configuration, credentials metadata, policies, aggregates, and audit records |
| Fast state/cache | Redis | Rate-limit state, short-lived authorization cache, counters, locks, and Celery broker/result needs as configured |
| Background processing | Celery | Usage aggregation, expiry tasks, webhooks, exports, notifications, and other asynchronous work |
| Dashboard authentication | JWT | Short-lived user access tokens and rotated/revocable refresh tokens |
| API-consumer authentication | DevVault API keys | Machine credential verification, independent of dashboard JWT authentication |
| Production server | ASGI/WSGI server behind reverse proxy/load balancer | Django process hosting and connection handling |
| Containerization | Docker/OCI | Reproducible application and worker deployment |

Recommended supporting tools include `pytest`, `pytest-django`, factory fixtures, OpenAPI schema generation, static analysis, structured JSON logging, error tracking, and metrics collection.

## 5. System Context and High-Level Architecture

```text
                         DEVVAULT CONTROL PLANE

 Dashboard / CLI / SDK
          |
          | JWT over TLS
          v
  +-------------------+       +-----------------------+
  | Load Balancer /   |------>| Django + DRF API      |
  | Reverse Proxy     |       | modular control plane |
  +-------------------+       +-----------+-----------+
                                          |
                     +--------------------+--------------------+
                     |                    |                    |
                     v                    v                    v
              +-------------+      +-------------+      +-------------+
              | PostgreSQL  |      | Redis       |      | Celery      |
              | source of   |      | cache and   |<---->| workers     |
              | truth       |      | fast state  |      | + scheduler |
              +-------------+      +-------------+      +-------------+


                           DEVVAULT ACCESS ENGINE

 API Consumer                Customer API / Gateway
      |                               |
      | dv_test_* or dv_live_*        | verify credential + request context
      +------------------------------>|
                                      v
                           +------------------------+
                           | Verification endpoint  |
                           | /api/v1/access/verify/ |
                           +-----------+------------+
                                       |
                      +----------------+----------------+
                      |                |                |
                      v                v                v
                Authentication   Scope policy    Rate limit/quota
                and key state    evaluation      evaluation
                      |                |                |
                      +----------------+----------------+
                                       |
                                       v
                         allow/deny + reason + metadata
                                       |
                                       v
                           async usage/decision event
                                       |
                                       v
                              OBSERVABILITY PLANE
                         usage, metrics, logs, audits
```

For the MVP, these logical planes can run in one Django codebase. They remain separate conceptual boundaries so the verification fast path can later be independently deployed and scaled.

## 6. Architectural Planes

### 6.1 Control plane

The control plane is the management surface used by DevVault users. It owns workflows such as account management, organization membership, project and environment configuration, API-service registration, key lifecycle commands, policy configuration, usage reporting, and audit review.

The control plane prioritizes correctness, clear authorization, and administrator usability. It may use PostgreSQL directly and invalidate or refresh access-engine caches after security-relevant changes.

### 6.2 Access engine

The access engine is the latency-sensitive decision path used for API-consumer requests. It authenticates a presented key, checks key and parent-resource status, evaluates permissions/scopes, consumes rate-limit capacity, checks quotas, and returns a structured decision.

It must fail securely, avoid cross-tenant lookups, minimize database work, and expose stable machine-readable denial reasons. It does not implement customer business authorization such as whether a user owns a particular invoice.

### 6.3 Observability plane

The observability plane captures the operational and business facts generated by both other planes. It includes structured application logs, metrics, traces, usage events and aggregates, security alerts, and immutable audit records.

Usage telemetry and audit history are related but not interchangeable:

- **Usage data** answers how much and how often an API was used.
- **Audit data** answers who changed or attempted what, when, where, and with what outcome.
- **Operational telemetry** answers whether DevVault itself is healthy and performant.

## 7. Proposed Repository Structure

```text
devvault-backend/
|
|-- manage.py
|-- pyproject.toml
|-- requirements/                 # optional compiled dependency files
|   |-- base.txt
|   |-- development.txt
|   `-- production.txt
|-- .env.example                  # safe placeholders only
|-- .gitignore
|-- README.md
|-- DEVVAULT_ARCHITECTURE.md
|
|-- config/
|   |-- __init__.py
|   |-- urls.py
|   |-- asgi.py
|   |-- wsgi.py
|   |-- celery.py
|   `-- settings/
|       |-- __init__.py
|       |-- base.py
|       |-- development.py
|       |-- production.py
|       `-- test.py
|
|-- apps/
|   |-- __init__.py
|   |
|   |-- core/
|   |   |-- apps.py
|   |   |-- models.py             # abstract/shared persistence primitives only
|   |   |-- exceptions.py
|   |   |-- pagination.py
|   |   |-- responses.py
|   |   |-- middleware.py
|   |   |-- logging.py
|   |   |-- types.py
|   |   `-- tests/
|   |
|   |-- accounts/
|   |   |-- models.py
|   |   |-- services.py
|   |   |-- selectors.py
|   |   |-- validators.py
|   |   |-- permissions.py
|   |   |-- tasks.py
|   |   |-- admin.py
|   |   |-- migrations/
|   |   `-- tests/
|   |
|   |-- organizations/
|   |   |-- models.py
|   |   |-- services.py
|   |   |-- selectors.py
|   |   |-- validators.py
|   |   |-- permissions.py
|   |   |-- tasks.py
|   |   |-- admin.py
|   |   |-- migrations/
|   |   `-- tests/
|   |
|   |-- projects/
|   |   |-- models.py
|   |   |-- services.py
|   |   |-- selectors.py
|   |   |-- validators.py
|   |   |-- permissions.py
|   |   |-- tasks.py
|   |   |-- admin.py
|   |   |-- migrations/
|   |   `-- tests/
|   |
|   |-- credentials/
|   |   |-- models.py
|   |   |-- services.py
|   |   |-- selectors.py
|   |   |-- validators.py
|   |   |-- permissions.py
|   |   |-- hashing.py
|   |   |-- generators.py
|   |   |-- tasks.py
|   |   |-- admin.py
|   |   |-- migrations/
|   |   `-- tests/
|   |
|   |-- access/
|   |   |-- models.py             # policy configuration only
|   |   |-- services.py           # verification and policy evaluation
|   |   |-- selectors.py
|   |   |-- validators.py
|   |   |-- permissions.py
|   |   |-- evaluators/
|   |   |   |-- scopes.py
|   |   |   |-- rate_limits.py
|   |   |   `-- quotas.py
|   |   |-- tasks.py
|   |   |-- admin.py
|   |   |-- migrations/
|   |   `-- tests/
|   |
|   |-- usage/
|   |   |-- models.py
|   |   |-- services.py
|   |   |-- selectors.py
|   |   |-- validators.py
|   |   |-- permissions.py
|   |   |-- aggregators.py
|   |   |-- tasks.py
|   |   |-- admin.py
|   |   |-- migrations/
|   |   `-- tests/
|   |
|   `-- audit/
|       |-- models.py
|       |-- services.py
|       |-- selectors.py
|       |-- validators.py
|       |-- permissions.py
|       |-- middleware.py
|       |-- tasks.py
|       |-- admin.py
|       |-- migrations/
|       `-- tests/
|
|-- api/
|   |-- urls.py
|   `-- v1/
|       |-- urls.py
|       |-- accounts/
|       |   |-- serializers.py
|       |   |-- views.py
|       |   `-- urls.py
|       |-- organizations/
|       |   |-- serializers.py
|       |   |-- views.py
|       |   `-- urls.py
|       |-- projects/
|       |   |-- serializers.py
|       |   |-- views.py
|       |   `-- urls.py
|       |-- credentials/
|       |   |-- serializers.py
|       |   |-- views.py
|       |   `-- urls.py
|       |-- access/
|       |   |-- serializers.py
|       |   |-- views.py
|       |   `-- urls.py
|       |-- usage/
|       |   |-- serializers.py
|       |   |-- views.py
|       |   `-- urls.py
|       `-- audit/
|           |-- serializers.py
|           |-- views.py
|           `-- urls.py
|
|-- tests/                         # cross-domain, integration, contract, and E2E tests
|   |-- integration/
|   |-- contract/
|   |-- security/
|   `-- performance/
|
|-- scripts/                       # maintenance and operational entry points
|-- docs/
|   |-- adr/
|   |-- api/
|   `-- runbooks/
|-- docker/
|   |-- app.Dockerfile
|   `-- entrypoint.sh
|-- compose.yaml
|-- templates/
|-- static/
`-- media/                         # avoid for durable production artifacts
```

Small domain modules may begin with a single `services.py` or `selectors.py` and become packages only when their size justifies it. Empty architectural folders should not be added merely to match the diagram.

## 8. Django App Boundaries and Responsibilities

### 8.1 `core`

**Purpose:** Framework-level primitives shared across bounded domains.

**Owns:**

- Abstract UUID primary-key and timestamp models.
- Shared exception taxonomy and API error envelope.
- Pagination, correlation IDs, request context, health/readiness endpoints, and safe logging utilities.
- Generic value types or helpers with no domain allegiance.
- Shared test utilities that do not create circular dependencies.

**Typical modules:** `models`, `exceptions`, `pagination`, `responses`, `middleware`, `logging`, `types`.

**Must not own:** Users, organizations, projects, API keys, policies, usage, audit records, or a generic dumping ground of unrelated utilities. It must not become a global service locator.

### 8.2 `accounts`

**Purpose:** DevVault human identity, authentication, and account lifecycle.

**Owns:**

- `User` model and account status.
- Registration, email verification, login, logout, password reset, password change, and token refresh/revocation workflows.
- MFA and external identity metadata when introduced.
- Personal profile and account-level security settings.

**Key models:** `User`, `RefreshTokenSession` or equivalent revocation/session record, optional `EmailVerificationToken`, optional `PasswordResetToken`.

**Services:** Register user, verify email, issue/rotate/revoke token sessions, disable account, change password.

**Selectors:** Retrieve current account, active sessions, and safe user identity summaries.

**Permissions/validators:** Account ownership, password policy, normalized unique email, login eligibility, token/session state.

**Must not own:** Organization roles, project access, API-consumer keys, service scopes, subscription entitlements, or API usage.

### 8.3 `organizations`

**Purpose:** Tenant boundary, organization lifecycle, membership, and organization-level roles.

**Owns:**

- `Organization` and `OrganizationMembership`.
- Invitations and membership lifecycle.
- Organization roles such as owner, administrator, developer, analyst, and billing administrator.
- Organization-level settings and status.

**Key models:** `Organization`, `OrganizationMembership`, optional `OrganizationInvitation`.

**Services:** Create organization, invite/accept member, change role, remove member, transfer ownership, suspend/reactivate tenant.

**Selectors:** Organizations visible to a user, active membership lookup, member lists scoped to organization.

**Permissions/validators:** Tenant membership, role capabilities, last-owner protection, invitation expiry, slug/name constraints.

**Must not own:** Project configuration, keys, access scopes, usage counters, invoices, or global user authentication.

### 8.4 `projects`

**Purpose:** Organize tenant resources into deployable products, environments, and protected API surfaces.

**Owns:**

- `Project`, `Environment`, and `APIService`.
- Test/live environment metadata and lifecycle.
- API service identity, status, audience, and optional upstream metadata.
- Project-level member overrides only if the product explicitly requires them.

**Key models:** `Project`, `Environment`, `APIService`, optional `ProjectMembership` in a later release.

**Services:** Create/archive project, provision canonical environments, create/disable service, rotate non-secret service identifiers.

**Selectors:** Tenant-scoped project tree, environment and service lookup, active service configuration.

**Permissions/validators:** Organization capability checks, unique names/slugs within parent, environment-type immutability rules, archive dependency checks.

**Must not own:** API-key material, key hashing, permission evaluation, counters, usage aggregation, or audit persistence.

### 8.5 `credentials`

**Purpose:** Secure API-consumer credential issuance, storage, rotation, revocation, and authentication.

**Owns:**

- `APIKey` metadata and irreversible verifier/digest.
- Key generation, prefix parsing, hashing, verification, one-time reveal, expiry, rotation, and revocation.
- Credential status and last-used metadata.
- Key naming and safe display fingerprint.

**Key models:** `APIKey`; optional `APIKeyRotation` or credential-family metadata later.

**Services:** Issue key, authenticate presented key, rotate key with optional overlap, revoke key, expire keys, update last-used information asynchronously.

**Selectors:** Key metadata lists scoped through organization/project/environment; candidate retrieval by non-secret key ID.

**Permissions/validators:** Key-management capability, expiration bounds, environment-prefix match, allowed key state transitions.

**Must not own:** Scope definitions, authorization evaluation, rate-limit algorithms, usage facts, human login tokens, or customer business authorization.

### 8.6 `access`

**Purpose:** Machine-request authorization and policy enforcement.

**Owns:**

- `Permission`, `RateLimitPolicy`, and `QuotaPolicy` configuration.
- Scope assignment to keys or policy bindings.
- Verification orchestration after credential authentication.
- Permission, rate-limit, and quota evaluators.
- Stable allow/deny decision schema and reason codes.

**Key models:** `Permission`, `APIKeyPermission` or equivalent binding, `RateLimitPolicy`, `QuotaPolicy`, policy bindings.

**Services:** Verify access request, bind/unbind permissions, create/update policies, invalidate policy cache.

**Selectors:** Effective policies and permissions for a tenant/environment/service/key; policy configuration lists.

**Permissions/validators:** Control-plane authority to manage policies, valid scope syntax, policy hierarchy conflicts, positive windows/limits, supported quota periods.

**Must not own:** Raw-key generation/storage, project lifecycle, durable usage analytics, human authentication, audit-log storage, or endpoint-specific business authorization within customer applications.

### 8.7 `usage`

**Purpose:** Capture, aggregate, query, retain, and export API consumption data.

**Owns:**

- `UsageEvent` and `UsageAggregate`.
- Usage ingestion contracts, deduplication, batching, retention, rollups, and reporting queries.
- Meter definitions needed for product usage and future billing.

**Key models:** `UsageEvent`, `UsageAggregate`, optional `Meter`, optional ingestion-deduplication record.

**Services:** Record event, ingest batch, aggregate time bucket, rebuild rollup, export usage.

**Selectors:** Time-series and grouped usage by organization, project, environment, service, key fingerprint, decision, and status.

**Permissions/validators:** Tenant-scoped reporting access, allowed dimensions, bounded date ranges, ingestion schema, event idempotency key.

**Must not own:** Rate-limit enforcement state, credential validation, invoices/payment collection, audit history, or arbitrary raw request/response bodies.

### 8.8 `audit`

**Purpose:** Tamper-resistant security and administrative accountability.

**Owns:**

- `AuditLog` persistence and query interface.
- Canonical event taxonomy for security-relevant and administrative actions.
- Actor, target, tenant, request, source, result, and safe before/after metadata.
- Retention/export policies for audit data.

**Key models:** `AuditLog`.

**Services:** Append audit event, safely serialize changes, export tenant audit history.

**Selectors:** Tenant-scoped immutable audit queries with strict pagination and filters.

**Permissions/validators:** Audit viewer/export capability, valid event category and outcome, redaction enforcement.

**Must not own:** General debug logs, usage analytics, business event sourcing, API-key secrets, or mutation/update/delete workflows for existing audit records.

## 9. Domain Model and Relationships

```text
User
  1
  |
  | *
OrganizationMembership * -------- 1 Organization
                                          |
                                          | 1
                                          | *
                                       Project
                                          |
                                          | 1
                                          | *
                                      Environment
                                          |
                          +---------------+---------------+
                          |                               |
                          | 1                             | 1
                          | *                             | *
                      APIService                      APIKey
                          |                               |
                          +---------------+---------------+
                                          |
                         +----------------+----------------+
                         |                |                |
                         v                v                v
                    Permission     RateLimitPolicy    QuotaPolicy
                         ^                ^                ^
                         +----------------+----------------+
                                          |
                                          v
                                      UsageEvent
                                          |
                                          v
                                    UsageAggregate

Organization / Project / Environment / APIService / APIKey
                         |
                         `-------------------------------> AuditLog
```

### 9.1 Core relationships

| Model | Parent/scope | Key relationship or constraint |
|---|---|---|
| `User` | Global identity | Email is normalized and unique; account status gates dashboard access. |
| `Organization` | Tenant root | All tenant-owned resources resolve to exactly one organization. |
| `OrganizationMembership` | User + organization | Unique active membership per user/organization; holds role and status. |
| `Project` | Organization | Unique slug/name policy within organization; can be archived, not silently deleted. |
| `Environment` | Project | Explicit `test` or `live` type; unique name/type within project. |
| `APIService` | Environment | Defines the protected service/audience within one environment. |
| `APIKey` | Environment and normally service | Stores key ID, safe prefix/fingerprint, verifier, status, expiry, and metadata—never raw key. |
| `Permission` | Service or project policy namespace | Stable machine-readable scope such as `orders:read`. |
| `RateLimitPolicy` | Environment/service/key binding | Defines capacity, window, algorithm, dimension, and precedence. |
| `QuotaPolicy` | Environment/service/key binding | Defines longer-period consumption allowance and reset behavior. |
| `UsageEvent` | Organization/project/environment/service/key | Append-oriented consumption fact with event ID and safe dimensions. |
| `UsageAggregate` | Meter + time bucket + dimensions | Unique bucket/dimension tuple; rebuilt from events when necessary. |
| `AuditLog` | Organization plus actor/target | Append-only record of security or administrative action. |

Use database foreign keys and uniqueness/check constraints as defense in depth. A child resource's organization should be derived from or validated against its parent chain; denormalized `organization_id` fields may be added for query performance only with enforced consistency.

## 10. Authentication Systems Must Remain Separate

### 10.1 Dashboard user authentication

```text
Human user -> email/password or SSO -> JWT access token
           -> DevVault control-plane API
```

- Used by developers and administrators managing DevVault resources.
- Uses short-lived signed access tokens.
- Uses rotated, revocable refresh tokens or server-tracked sessions.
- Supports email verification, password security, account disabling, MFA, and SSO evolution.
- Authorization is based on organization membership and explicit capabilities.

### 10.2 API-consumer key authentication

```text
API consumer -> dv_test_* or dv_live_* -> customer API/gateway
             -> DevVault access verification -> allow/deny
```

- Used by software calling a customer's protected API.
- Uses a DevVault-generated opaque credential, not a JWT issued to a dashboard user.
- Is scoped to one environment and normally one API service.
- Is evaluated against status, expiry, permissions, rate limits, and quotas.
- Does not create a DevVault dashboard session and cannot access management endpoints.

No authentication backend, endpoint, serializer, or permission class should silently accept both credential types.

## 11. API Key Format, Lifecycle, and Secure Storage

### 11.1 Recommended format

```text
dv_<environment>_<key_id>_<secret>

Examples:
dv_test_k7F3a2_<high-entropy-secret>
dv_live_p9Q8b4_<high-entropy-secret>
```

- `dv_test_` and `dv_live_` make environment intent visible.
- `key_id` is a non-secret lookup identifier and must be unguessable enough to resist enumeration.
- `secret` is generated with a cryptographically secure random-number generator and sufficient entropy (at least 256 random bits before encoding is recommended).
- The database stores only a safe display prefix/fingerprint and verifier, never the complete key or secret.

### 11.2 Storage and verification strategy

For the high-throughput verification path, store a deterministic keyed digest such as `HMAC-SHA-256(server_pepper, full_key_or_secret)` and compare digests using a constant-time comparison function. The pepper must live in a managed secrets system or KMS-protected configuration, separate from the database, and support versioning for rotation.

An adaptive password hash such as Argon2id may be considered for lower-throughput deployments, but its cost must be performance-tested. Plain SHA-256 without a secret pepper is not an acceptable storage design.

The non-secret `key_id` selects a single candidate record before digest computation. Verification must also confirm the parsed environment prefix matches the credential's stored environment.

### 11.3 One-time reveal

1. Generate the secret in application memory.
2. Construct the complete key.
3. Compute and persist only the verifier, key ID, fingerprint, prefix, pepper version, and metadata within a transaction.
4. Return the complete key exactly once in the successful creation response.
5. Do not place it in asynchronous messages, analytics, audit metadata, URLs, error trackers, or logs.
6. If the user loses the key, issue a replacement; never attempt recovery.

### 11.4 Lifecycle states

```text
created/active --> expiring --> expired
      |              |
      +--------------+--> revoked
      |
      `--> rotated --> revoked after optional bounded overlap
```

- **Active:** Eligible for evaluation.
- **Expired:** Automatically denied after `expires_at`.
- **Revoked:** Immediately denied and never reactivated.
- **Rotated:** Replacement issued; old key may remain active only for a short, explicit overlap window.
- **Compromised:** A revocation reason that triggers additional alerting and audit treatment.

Revocation and policy changes must invalidate relevant cache entries immediately or make cached data unusable through versioned configuration.

## 12. Request Verification Flow

```text
1. Receive credential and request context
        |
2. Parse format and environment prefix
        | invalid -> deny: invalid_credential
3. Locate candidate by non-secret key_id
        | absent -> deny with non-enumerating response
4. Compute verifier and constant-time compare
        | mismatch -> deny with same public auth response
5. Check key, environment, service, project, and organization status
        | inactive/expired/revoked -> deny
6. Validate requested audience/service and environment
        | mismatch -> deny
7. Resolve effective permissions/scopes
        | insufficient -> deny: insufficient_scope
8. Atomically consume rate-limit capacity in Redis
        | exhausted -> deny: rate_limited
9. Check/consume quota using authoritative counter strategy
        | exhausted -> deny: quota_exceeded
10. Return signed or authenticated decision payload as required
11. Emit safe usage/decision event asynchronously
```

The request context should include the credential, requested service/audience, required scopes, HTTP method/path template where used, a unique request or idempotency ID, and optional safe metering dimensions. Arbitrary customer-supplied strings must not become unbounded metric labels or cache keys.

The response should include `allowed`, a stable `reason_code`, key/service/environment identifiers safe for the caller, granted or missing scope metadata where appropriate, and rate-limit information. It must never echo the credential.

## 13. Permissions and Scopes

Scopes express what an API key may do within its assigned service. Use stable, lowercase, namespaced identifiers:

```text
orders:read
orders:write
customers:read
reports:export
```

Rules:

- Deny by default when a required scope is not granted.
- Treat scope changes as security changes and audit them.
- Scope grants must not cross environment or service boundaries.
- Define whether multiple required scopes use `all` or `any`; default to `all` for explicit authorization.
- Avoid wildcard scopes in V1. If introduced later, define matching rules precisely.
- Control-plane roles and API-consumer scopes are separate concepts.
- DevVault scopes authorize access to an API capability, not access to a particular customer-owned record inside that API.

## 14. Rate Limiting

Rate limits protect short windows and burst capacity. Redis is the primary enforcement store because increments and expiry can be atomic and low-latency.

### 14.1 Recommended design

- Begin with a fixed-window counter or token-bucket algorithm implemented atomically, preferably through a Redis script/function.
- Key counters by environment, policy, key or configured dimension, and window.
- Include tenant identity in every logical key; use opaque IDs rather than user-controlled strings.
- Store policy configuration in PostgreSQL and cache resolved policies in Redis.
- Return standard limit, remaining, reset, and retry metadata.
- Define deterministic precedence: explicit key policy, then service policy, then environment/project default.
- Rate-limit the verification endpoint itself independently to resist abuse.

### 14.2 Failure behavior

The failure mode must be a documented product decision per policy class. Security-sensitive or paid-resource limits should normally fail closed when authoritative enforcement is unavailable. A carefully bounded fail-open option may be supported later for customer availability requirements, but it must be explicit, observable, and never the silent default.

## 15. Quotas

Quotas enforce consumption across longer periods, for example daily, monthly, or billing-cycle usage.

- Policies define meter, allowance, period, timezone/reset rule, scope, and overage behavior.
- Enforcement counters need atomic updates and a durable reconciliation path.
- Redis may provide fast counters; PostgreSQL usage events/aggregates provide durable reconciliation.
- A quota decision must have a documented consistency model. Hard financial limits require reservation or strongly consistent consumption semantics.
- Retries must not double-consume quota; use a request/idempotency identifier where clients may retry.
- Policy changes and resets are audit events.
- V1 should use a small set of supported periods and meters rather than arbitrary formulas.

## 16. Usage Metering

Usage metering records safe, structured facts about access decisions and consumption.

### 16.1 Suggested event fields

```text
event_id
occurred_at
received_at
organization_id
project_id
environment_id
api_service_id
api_key_id or safe fingerprint
meter
quantity
decision (allowed/denied)
reason_code
status_code_class (optional)
latency_ms (optional)
request_id
schema_version
safe dimensions
```

Do not store the raw API key, authorization header, arbitrary request body, response body, or sensitive query parameters.

### 16.2 Processing model

- Generate globally unique event IDs.
- Publish or enqueue events after the access decision without materially extending response latency.
- Batch inserts when safe.
- Make ingestion idempotent on `event_id`.
- Roll events into hourly/daily aggregates using Celery tasks.
- Reconcile aggregates and quota counters from durable events.
- Apply explicit retention periods and partition high-volume tables by time when justified.
- Keep billing-grade meter rules versioned and reproducible.

## 17. Audit Logging

Audit logging is mandatory for security-relevant and administrative activity.

Record at minimum:

- Login success/failure and important account-security changes.
- Organization creation, suspension, ownership transfer, invitations, joins, removals, and role changes.
- Project, environment, and service creation/status changes.
- API-key creation, rotation, expiration, and revocation using only safe identifiers.
- Scope/policy grants, removals, and edits.
- Audit/usage exports and other sensitive data access.
- Administrative or support impersonation when later introduced.

An audit record should include timestamp, organization, actor type and ID, action, target type and ID, outcome, request/correlation ID, safe source information, and redacted before/after changes. Audit rows are append-only. Corrections are new events, not mutations. Database access for the application role should prohibit updating or deleting audit records where practical.

## 18. Environment Separation

Test and live are separate security and data domains even when hosted in the same deployment.

- Test keys begin with `dv_test_`; live keys begin with `dv_live_`.
- A key belongs to exactly one environment.
- Verification requires the prefix, stored environment, requested service, and requested environment to agree.
- Policies, counters, quota periods, usage, cache keys, exports, and analytics are environment-scoped.
- The UI and API make live operations visually and semantically explicit.
- Test data must never consume live entitlements or appear in live billing totals.
- Live credentials should have stricter issuance permissions and alerting.

Physical database separation is not required for MVP, but logical isolation must be enforceable and tested. Enterprise deployments may later support separate regional or dedicated data planes.

## 19. API Versioning and Suggested Endpoints

All public endpoints use a major version prefix:

```text
/api/v1/
```

Breaking behavior, field, or semantic changes require a new major API version or an explicit compatibility strategy. Additive fields may be introduced within a version. Publish an OpenAPI contract and stable error schema.

### 19.1 Control-plane endpoints

```text
POST   /api/v1/auth/register/
POST   /api/v1/auth/login/
POST   /api/v1/auth/refresh/
POST   /api/v1/auth/logout/
GET    /api/v1/me/

GET    /api/v1/organizations/
POST   /api/v1/organizations/
GET    /api/v1/organizations/{organization_id}/
GET    /api/v1/organizations/{organization_id}/members/
POST   /api/v1/organizations/{organization_id}/invitations/

GET    /api/v1/organizations/{organization_id}/projects/
POST   /api/v1/organizations/{organization_id}/projects/
GET    /api/v1/projects/{project_id}/
GET    /api/v1/projects/{project_id}/environments/
POST   /api/v1/environments/{environment_id}/services/

GET    /api/v1/environments/{environment_id}/keys/
POST   /api/v1/environments/{environment_id}/keys/
POST   /api/v1/keys/{key_id}/rotate/
POST   /api/v1/keys/{key_id}/revoke/

GET    /api/v1/services/{service_id}/permissions/
POST   /api/v1/services/{service_id}/permissions/
GET    /api/v1/services/{service_id}/rate-limit-policies/
GET    /api/v1/services/{service_id}/quota-policies/

GET    /api/v1/organizations/{organization_id}/usage/
GET    /api/v1/organizations/{organization_id}/audit-logs/
```

### 19.2 Access endpoint

```text
POST   /api/v1/access/verify/
```

Bulk verification or local cached verification may be added only after a clear threat model and consistency contract.

### 19.3 Endpoint conventions

- Use opaque UUIDs or similarly non-sequential public identifiers.
- Scope nested list/create endpoints through their explicit parent.
- Use an `Idempotency-Key` for retryable credential creation and other sensitive mutations.
- Use cursor pagination for high-volume, append-oriented data.
- Provide stable error codes independent of human-readable messages.
- Do not reveal whether a key ID exists when authentication fails.
- Apply consistent timestamps in UTC using ISO 8601.

## 20. Service-Layer Architecture

Business rules belong in domain services, not in views, serializers, model `save()` overrides, signals, or Celery task bodies.

```text
HTTP Request
    |
    v
View / ViewSet        authentication, permission entry, orchestration, response
    |
    v
Serializer            transport validation and representation
    |
    v
Domain Service        use case, business rules, transaction, audit scheduling
    |
    +------> Selector read/query path
    |
    +------> Model persistence and constraints
    |
    `------> on-commit event/task dispatch
```

### 20.1 Responsibility conventions

| Layer | Does | Does not do |
|---|---|---|
| Model | Defines persistence, relationships, local invariants, and constraints | Orchestrate multi-model workflows or call external systems from `save()` |
| Selector | Performs named, optimized, authorization-scoped reads | Mutate data or hide write side effects |
| Service | Executes a business use case, enforces invariants, controls transactions, emits audit/events | Depend on HTTP request/response objects |
| Validator | Checks reusable value or command validity | Perform large query workflows or persist state |
| Serializer | Validates/parses API payloads and renders representations | Contain core business decisions or cross-domain transactions |
| View/ViewSet | Handles HTTP concerns, invokes selectors/services, maps known errors | Directly implement credential, policy, tenancy, or lifecycle logic |
| Permission class | Performs coarse request/object access gate | Replace selector query scoping or service-level invariant checks |
| Celery task | Provides retryable asynchronous entry point into an idempotent service | Contain unique business logic available nowhere else |

Use `transaction.atomic()` for multi-write use cases. Dispatch tasks and external events with `transaction.on_commit()` so workers do not observe rolled-back or uncommitted state. Signals are reserved for framework integration or truly passive side effects and must not hide critical workflows.

### 20.2 Cross-app rules

- Reference another domain's public service/selector interface rather than modifying its models directly.
- Avoid circular app imports; shared contracts should be small and explicit.
- Database foreign keys across apps are allowed when the domain relationship is real.
- Cross-domain write workflows have one owning orchestrator service.
- Add ADRs before moving ownership or duplicating domain state.

## 21. Data and Infrastructure Responsibilities

### 21.1 PostgreSQL

PostgreSQL is the authoritative store for:

- Users, organizations, memberships, projects, environments, and API services.
- API-key metadata and cryptographic verifiers.
- Permission, rate-limit, and quota policy configuration.
- Durable usage events and aggregates appropriate to the current scale.
- Immutable audit history.
- Idempotency and outbox records where required.

Use foreign keys, check constraints, partial unique indexes, appropriate indexes, transactional locking, point-in-time recovery, encrypted backups, and tested restoration. High-volume usage and audit tables should evolve toward time partitioning and independent retention management.

### 21.2 Redis

Redis is responsible for:

- Atomic rate-limit state.
- Fast quota counters when paired with durable reconciliation.
- Short-lived credential-status and policy caches.
- Cache invalidation/version markers.
- Carefully bounded idempotency or distributed-lock records.
- Celery broker/result roles if chosen operationally.

Redis is not the sole durable source of truth for credentials, policy configuration, billing-grade usage, or audit logs. All keys require namespace, environment/tenant scope, schema version, and TTL where applicable. Separate logical/physical Redis deployments for cache, enforcement, and task brokering may be introduced as scale and failure-domain needs grow.

### 21.3 Celery workers and scheduler

Celery handles:

- Usage ingestion, batching, aggregation, and reconciliation.
- Key-expiration sweeps and expiry notifications.
- Webhook delivery and retry in V2.
- Email/notification delivery.
- Usage/audit exports.
- Cache warming or invalidation fan-out when necessary.
- Retention and maintenance tasks.
- Billing sync and entitlement reconciliation in later phases.

Tasks must be idempotent, observable, time-bounded, and safe to retry. Route workloads to separate queues by priority and resource profile. Use exponential backoff with jitter and dead-letter/failure handling. Never pass raw API keys in task payloads.

## 22. Caching Strategy

Cache only data with a defined owner, key schema, TTL, and invalidation rule.

Recommended cached objects:

- Key status and safe metadata after candidate lookup.
- Effective permissions and policy configuration.
- Organization/project/environment/service active-state chain.
- Short-lived dashboard list/read responses where justified.

Rules:

- Cache keys include schema version and all security-relevant scope IDs.
- Security mutations invalidate synchronously after commit or increment a version that immediately makes old entries unreachable.
- TTL is a backstop, not the only revocation mechanism.
- Negative credential results may be cached briefly to reduce abuse, without enabling enumeration.
- Do not cache raw credentials, authorization headers, secrets, or unredacted personal data.
- Prevent cache stampedes with short locks, request coalescing, or jittered TTLs where necessary.
- Measure hit ratio, stale-read risk, latency, and eviction behavior before expanding cache use.

## 23. Security Requirements

### 23.1 Mandatory controls

- Enforce TLS for every external and service-to-service connection; use modern configurations and automated certificate rotation.
- Store only keyed digests/verifiers for API keys and one-way password hashes using an approved adaptive algorithm.
- Keep peppers, signing keys, database credentials, and third-party secrets in a managed secret store; never commit them.
- Encrypt databases, backups, queues, and sensitive fields at rest where applicable.
- Use constant-time digest comparison for credential verification.
- Never log raw keys, JWTs, cookies, authorization headers, passwords, reset tokens, or secret request fields.
- Redact secrets at request middleware, structured logger, error tracker, tracing, and support-tool boundaries.
- Enforce tenant scoping in selectors, services, object permissions, cache keys, tasks, and exports.
- Use least-privilege database roles, cloud identities, queues, and operator permissions.
- Apply CSRF protection where cookies are used, strict CORS configuration, secure headers, and request-size limits.
- Rate-limit login, registration, password reset, key verification, and other abuse-sensitive endpoints.
- Rotate JWT signing keys, API-key peppers, infrastructure credentials, and encryption keys through documented procedures.
- Validate all lifecycle state transitions and archive rather than cascade-delete security history.
- Maintain append-only audit records for privileged actions.
- Scan dependencies, containers, and source for vulnerabilities and secrets in CI.
- Back up critical stores and test restoration routinely.

### 23.2 Tenant isolation

Tenant isolation is an invariant, not a view-level convenience:

- Start every tenant-owned query from the authenticated user's active organization membership or trusted credential parent chain.
- Never fetch an object globally and then rely only on a later permission check.
- Include organization/environment scope in uniqueness, cache, rate-limit, and idempotency keys.
- Reject mismatched parent IDs rather than silently re-parenting data.
- Test horizontal privilege escalation systematically.
- Consider PostgreSQL Row-Level Security later as defense in depth, not as a substitute for application scoping.

### 23.3 Key compromise and response

Provide immediate revocation, bounded cache invalidation, operator alerts for suspicious verification patterns, safe credential fingerprints, key-age reporting, and audit exports. Maintain runbooks for signing-key compromise, API-key pepper compromise, database exposure, and cross-tenant access incidents.

## 24. Observability, Monitoring, Logging, and Metrics

### 24.1 Structured logging

Emit JSON logs containing timestamp, severity, service, deployment version, environment, request/correlation ID, route template, outcome, safe actor or tenant ID, and latency. Use allowlisted fields. Never include secrets or unbounded request bodies.

### 24.2 Metrics

Track at minimum:

- Request rate, error rate, and latency percentiles by route class.
- Verification allow/deny rate by safe reason code.
- Verification latency and cache hit/miss rate.
- Rate-limit and quota denials.
- PostgreSQL connection usage, query latency, locks, replication lag, and storage.
- Redis latency, memory, eviction, errors, and command rate.
- Celery queue depth, task age, execution time, retries, failures, and dead letters.
- Usage-event ingestion lag and aggregate reconciliation drift.
- Authentication failures, key-creation/revocation activity, and anomalous tenant access patterns.

Avoid high-cardinality labels such as raw user IDs, key IDs, URLs, or arbitrary customer values in metrics. Put identifiers in structured logs/traces with appropriate access controls instead.

### 24.3 Tracing and alerting

- Propagate correlation/trace IDs through API, Redis/PostgreSQL calls, and task dispatch.
- Sample normal traffic and retain more error/security traces without capturing secrets.
- Alert on SLO breaches, sustained denial anomalies, worker backlog, failed aggregates, database saturation, Redis memory pressure, unusual credential failures, and audit pipeline failure.
- Define service-level indicators for access-engine availability and p95/p99 verification latency.

### 24.4 Health endpoints

- **Liveness:** Process can serve; does not require every dependency.
- **Readiness:** Required dependencies for that workload are reachable and migrations/configuration are compatible.
- Protect detailed diagnostics; public health responses reveal minimal information.

## 25. Testing Strategy

| Test layer | Focus |
|---|---|
| Unit | Validators, policy evaluators, key parsing/hashing, state transitions, and pure domain rules |
| Model/database | Constraints, indexes, transactions, locking, tenant relationships, and migration behavior |
| Service | Complete use cases, authorization invariants, audit emission, idempotency, and rollback behavior |
| API | Authentication type separation, permissions, validation, error schema, pagination, and version contract |
| Integration | PostgreSQL, Redis atomic algorithms, Celery dispatch/retry, caching, and external adapters |
| Security | Cross-tenant access, environment crossover, secret leakage, enumeration resistance, replay/abuse, and privilege escalation |
| Contract | OpenAPI compatibility, SDK-facing behavior, usage-event schema, and webhook schemas |
| Performance | Verification throughput/latency, cache behavior, rate-limit atomicity, and high-volume ingestion |
| Resilience | Redis/database degradation, worker backlog, retry storms, restoration, and cache invalidation |
| End-to-end | User creates tenant/project/service/key, consumer verifies, policy denies/allows, usage/audit become visible |

Required test cases include:

- A user cannot read or mutate another organization's resources by changing identifiers.
- A test key cannot verify against a live environment or service.
- Revoked, expired, malformed, and incorrectly hashed keys are denied without enumeration clues.
- A newly revoked key becomes unusable within the documented invalidation bound.
- Concurrent rate-limit and quota operations never permit unintended over-consumption beyond the documented tolerance.
- Retry does not duplicate key issuance, usage events, webhook delivery state, or quota consumption.
- Raw keys and authorization headers never appear in captured logs, task payloads, traces, audit records, or errors.
- Audit records are produced for every required administrative action and cannot be mutated through the product API.

Run fast unit/service tests on every change; run integration, migration, contract, security, and performance suites at appropriate CI and release gates.

## 26. Deployment Architecture

### 26.1 MVP deployment

```text
Internet
   |
DNS + TLS
   |
Load Balancer / Reverse Proxy
   |
   +--> Django web containers (control plane + access endpoint)
   |
   +--> Celery worker container(s)
   |
   `--> Celery scheduler (exactly one active scheduler)

Django/workers --> Managed PostgreSQL
Django/workers --> Managed Redis
Django/workers --> Secret manager
Django/workers --> Logs, metrics, traces, error tracking
```

MVP requirements:

- Containers are immutable and configured through environment-specific settings and secret references.
- Database migrations run as a controlled release job, not independently in every web replica.
- PostgreSQL and Redis are managed services where possible.
- Automated encrypted backups and point-in-time recovery are enabled.
- Staging and production are separate deployments with separate secrets and data stores.
- Web and worker processes scale independently.
- Deployments support rolling or blue/green release with readiness checks and rollback.

### 26.2 Production evolution

```text
Global DNS / Traffic Management
            |
       CDN / WAF / DDoS controls
            |
    Regional load balancers
            |
    +-------+-------------------+
    |                           |
Control-plane services     Access-engine fleet
    |                           |
    +-------+-------------------+
            |
 PostgreSQL primary + replicas / partitioned stores
 Redis enforcement clusters + separate cache/broker clusters
 Durable event bus / stream
 Worker fleets by queue and workload
 Object storage / warehouse for long-term analytics
 Central secrets, telemetry, and incident response
```

## 27. Infrastructure Evolution

### Phase A: Modular monolith, single region

- One repository and deployable Django application.
- Managed PostgreSQL and Redis.
- Celery workers and scheduler.
- Access verification is a separate endpoint and code boundary inside the monolith.
- Durable usage events remain in PostgreSQL at manageable volume.

### Phase B: Independent scaling

- Separate web deployments for control-plane and access-engine workloads while sharing domain packages.
- Read replicas for reporting.
- Redis separated by enforcement, cache, and broker failure domains.
- Dedicated queues and autoscaling worker pools.
- Time-partitioned usage and audit tables.

### Phase C: Event-driven data plane

- Introduce a durable stream/event bus for usage and decision events.
- Move long-term analytics to columnar storage or a warehouse.
- Extract usage ingestion/aggregation and webhook delivery as independent services if operationally justified.
- Provide regional access-engine deployments with replicated, versioned policy snapshots.

### Phase D: Distributed and enterprise platform

- Multi-region access decisions with clearly defined consistency and revocation propagation SLOs.
- Tenant data residency and regional routing.
- Dedicated enterprise deployments or isolation tiers.
- Central entitlement and billing platform.
- Advanced compliance evidence, SIEM exports, SCIM, SSO, and customer-managed key options.

Extraction is driven by measured scale, reliability, team ownership, or regulatory needs—not by abstract preference. Domain contracts and versioned events established in the monolith should make extraction possible.

## 28. V1 / MVP Feature Set

- Email/password account registration, verification, login, refresh, logout, and password reset.
- Organization creation and role-based memberships.
- Projects with canonical test and live environments.
- API-service creation and status management.
- Secure `dv_test_` and `dv_live_` key generation, one-time reveal, list, expiry, rotation, and revocation.
- Permission/scope definitions and key grants.
- Configurable rate-limit policies with Redis enforcement.
- Basic daily/monthly quotas with clear consistency behavior.
- Versioned credential-verification endpoint.
- Usage-event ingestion and basic hourly/daily aggregates.
- Usage dashboard/query API with bounded filters.
- Immutable audit log and audit viewer.
- API documentation/OpenAPI contract.
- Core operational telemetry, alerts, backup, recovery, and deployment automation.

## 29. V2 Features

- Signed webhooks for key, policy, quota, and usage events with retry and delivery history.
- Subscription billing and payment-provider integration.
- Entitlements and plan-aware quotas.
- Usage-based billing meters, invoice inputs, and reconciliation.
- Email/in-app notifications for expiry, quota thresholds, anomalies, and invitations.
- Scheduled usage and audit exports.
- Improved key rotation overlap and automated rotation workflows.
- Additional rate-limit algorithms and customer-configurable policy precedence.
- MFA and richer organization administration.

## 30. V3 Features

- Hosted developer portal and API documentation experience.
- Self-service application registration and key requests/approvals.
- Enterprise SSO/SAML/OIDC, SCIM, custom roles, and fine-grained RBAC.
- Regional/data-residency controls and dedicated deployments.
- SIEM, gateway, cloud, and incident-response integrations.
- Formal compliance program and evidence tooling for SOC 2/ISO 27001 and applicable privacy obligations.
- Official SDK repositories, CLI, gateway plugins, framework middleware, examples, and compatibility testing.
- Advanced anomaly detection, credential risk scoring, and automated response.
- Policy-as-code and approval workflows.
- Customer-managed encryption-key options where justified.

## 31. V1 Non-Goals

- Building or proxying the customer's full business API.
- Record-level business authorization inside customer applications.
- A general-purpose OAuth/OIDC authorization server.
- Arbitrary user-authored policy code.
- Global active-active multi-region deployment.
- A complete billing, invoicing, taxation, and payment platform.
- A hosted developer marketplace.
- Enterprise SSO, SCIM, SIEM, or formal compliance certification at launch.
- Unlimited custom analytics dimensions or permanent raw-event retention.
- Supporting every rate-limit algorithm, database, message broker, or deployment target.
- Microservice extraction before operational evidence requires it.

## 32. Suggested Build Order

1. **Foundation:** Repository, settings, local containers, CI, health endpoints, logging, exception format, UUID/timestamp primitives, PostgreSQL, Redis, and Celery.
2. **Accounts:** Custom `User` model before first production migration, authentication, email verification, JWT session/refresh lifecycle, and account security tests.
3. **Organizations:** Tenant model, memberships, roles/capabilities, invitations, and exhaustive tenant-isolation tests.
4. **Projects:** Projects, test/live environments, API services, lifecycle rules, and scoped selectors.
5. **Credentials:** Key format, secure generation/verifier, one-time reveal, expiry, rotation, revocation, and log-redaction tests.
6. **Access policies:** Permissions/scopes, rate-limit policies, quota policies, precedence, and cache invalidation.
7. **Verification fast path:** Stable contract, credential authentication, parent-state checks, evaluators, Redis atomics, decision codes, performance budget, and abuse controls.
8. **Usage:** Event ingestion, idempotency, aggregation, reporting queries, reconciliation, and retention.
9. **Audit:** Append-only event taxonomy, mutation hooks through services, viewer/export permissions, and immutability controls. Critical audit capture should be introduced alongside earlier security workflows rather than deferred entirely to this step.
10. **Operational hardening:** Alerts, dashboards, restore tests, load tests, threat review, runbooks, deployment rollback, and release gates.
11. **Public integration:** OpenAPI publication, reference middleware/SDK, examples, and end-to-end onboarding documentation.

Each step should ship with migrations, tests, API documentation, audit coverage, and observability—not as separate cleanup phases.

## 33. Monetization and Entitlement Readiness

The MVP need not charge customers, but its domain should preserve the facts needed for later monetization.

### 33.1 Capabilities to design for

- Versioned meters and billable-event definitions.
- Idempotent, immutable usage facts and reproducible aggregates.
- Organization subscription and plan association.
- Entitlements such as allowed projects, services, keys, retention, rate limits, and premium features.
- Trial periods, grace periods, suspension, and plan changes.
- Quota threshold and overage behavior.
- Usage export to a billing provider with reconciliation status.
- Invoice-period snapshots so later policy edits do not rewrite historical charges.
- Billing administrator role and auditable billing actions.

### 33.2 Boundary rule

The `usage` app owns consumption facts; a future `billing` app should own subscriptions, prices, invoices, payment-provider state, and bill computation. A future `entitlements` app may own effective plan capabilities if that responsibility becomes complex. Neither billing nor entitlements should own API access events or key verification.

## 34. Conventions and Architecture Guardrails

### 34.1 Code and data conventions

- Use UUIDs/opaque IDs for public resources.
- Store timestamps in UTC and expose ISO 8601.
- Use explicit status fields and validated state transitions.
- Use database constraints for invariants that the database can enforce.
- Use type hints on service and selector interfaces.
- Keep functions and transactions focused on one named use case.
- Prefer explicit names such as `revoke_api_key` over generic CRUD helpers.
- Avoid soft deletion as a universal pattern; choose archive, revoke, expire, or immutable retention according to domain meaning.
- Index foreign keys, status/time filters, tenant-scoped list queries, key lookup IDs, and aggregate dimensions based on measured query plans.

### 34.2 API conventions

- Authentication and authorization are distinct steps.
- Deny by default and return stable reason/error codes.
- Never expose secrets after initial creation.
- Use consistent pagination, filtering, ordering, validation, and error envelopes.
- Publish deprecation policy and compatibility windows.
- Require idempotency for retry-sensitive create/consume operations.
- Bound collection queries, export ranges, payload sizes, and client-controlled dimensions.

### 34.3 Dependency guardrails

- `core` may not import domain apps.
- Domain apps should not import API views/serializers.
- API modules may import public domain services/selectors.
- Celery tasks call domain services; domain services do not depend on Celery task implementations.
- Access evaluators use explicit inputs and return explicit decisions, making them independently testable.
- External providers are wrapped behind adapters/interfaces and tested with contract fixtures.

### 34.4 Change-management guardrails

- Record material decisions in `docs/adr/`.
- Review migrations for locks, table rewrites, backfill strategy, and reversibility.
- Use expand/migrate/contract deployment patterns for breaking schema changes.
- Version events, webhooks, public APIs, and cryptographic formats.
- Threat-model new authentication, policy, billing, export, or integration features.
- Define retention, deletion, and compliance effects before collecting new data.
- Require security review for changes touching tenant scoping, credentials, authorization, cryptography, or secret handling.

## 35. Initial Architecture Decisions to Record

The following ADRs should be created early:

1. Modular monolith and app boundaries.
2. Custom user model and dashboard JWT session strategy.
3. API-key format, HMAC verifier, pepper storage, and rotation.
4. Organization membership roles and capability matrix.
5. Environment/service/key relationship and isolation rules.
6. Rate-limit algorithm, Redis atomicity, and failure behavior.
7. Quota consistency and reconciliation model.
8. Usage-event schema, retention, and aggregation.
9. Audit immutability and retention.
10. API versioning and error contract.
11. Transactional outbox/event dispatch decision when reliability requirements justify it.

## 36. Definition of Architectural Compliance

A feature is architecturally complete when:

- Its owning domain is clear.
- Tenant and environment scoping are enforced in queries and writes.
- Business logic is implemented in services/evaluators, not views.
- Database constraints and transaction boundaries protect critical invariants.
- Secrets and personal data have explicit storage, redaction, and retention treatment.
- Authentication, authorization, rate limiting, quotas, usage, and auditing remain correctly separated.
- The API contract and error behavior are documented and version-compatible.
- Unit, integration, security, and relevant performance tests exist.
- Logs, metrics, traces, alerts, and runbooks are proportionate to operational risk.
- Background work is idempotent and retry-safe.
- Material design changes are captured in an ADR and reflected here.

## 37. Conclusion

DevVault should begin as a disciplined Django modular monolith backed by PostgreSQL, Redis, and Celery. Its strength will come less from the number of services it runs and more from strict domain ownership, tenant and environment isolation, secure one-time credential issuance, low-latency policy enforcement, durable usage facts, and trustworthy audit history.

The control plane, access engine, and observability plane should remain explicit even while sharing a repository and deployment. This preserves a fast MVP path while allowing the verification and data pipelines to scale independently later. If the implementation follows the boundaries and guardrails in this document, DevVault can evolve from a single-region API-key management product into a distributed access, entitlement, metering, billing, and enterprise developer-platform foundation without requiring an avoidable rewrite of its core security model.
