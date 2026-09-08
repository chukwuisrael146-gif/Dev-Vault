from uuid import UUID

from apps.audit.models import AuditLog
from apps.core.context import correlation_id_context, source_ip_context
from apps.core.logging import redact_value


def record_event(
    *,
    action: str,
    target_id: UUID | None,
    actor_id: UUID | None = None,
    outcome: str = "success",
    organization_id: UUID | None = None,
    target_type: str = "accounts.User",
    changes: dict | None = None,
) -> None:
    """Persist safe account event identifiers in the caller's transaction."""
    AuditLog.objects.create(
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        outcome=outcome,
        request_id=correlation_id_context.get() or "",
        organization_id=organization_id,
        changes=redact_value(changes or {}),
        actor_type="user" if actor_id else "system",
        source_ip=source_ip_context.get(),
    )
