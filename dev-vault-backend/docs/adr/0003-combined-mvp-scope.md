# ADR 0003 Combined MVP scope and source precedence

Accepted for the user's complete backend implementation request on 2026-09-08.

The architecture is authoritative for the modular monolith, eight domain apps,
canonical service/environment scope, UUID identifiers, `/api/v1/` routing and error
envelope. The PRD supplies detailed acceptance criteria. The White Paper explains
product direction; commercial predictions are not implementation commitments.

Where release labels disagree, include the PRD's frontend-facing MVP requirements
rather than describing a smaller architecture-only implementation as complete.
This brings signed webhooks, bounded key rotation overlap, token-bucket limits,
exports and a reference Python/Django integration into the local delivery target.
Webhooks merit their own bounded domain when implemented, rather than adding
network delivery and secrets to `core`, `audit` or `usage`.

Use service-scoped permissions (architecture) rather than an ambiguous project-wide
grant. Support namespaced scope names with either `:` or `.` separators, but no
wildcards. Environment/service bindings cannot be changed after creation.

Use PostgreSQL as authoritative for quota reservations, request deduplication and
decision-event durability. Redis enforces short-window rate policies, not durable
quota balances. Verification requires trusted integration context in addition to
the consumer's presented key, so a consumer cannot weaken required scopes or
metering units by directly changing verification parameters.

No external release, purchases or production infrastructure changes are part of the
local build. Later billing/SSO/SCIM/multi-region capabilities and independently
verified operational gates remain explicit exclusions, not placeholders claimed
as delivered functionality.
