from uuid import UUID

from apps.audit.models import AuditLog
from apps.core.context import correlation_id_context


def record_event(
    *,
    action: str,
    target_id: UUID | None,
    actor_id: UUID | None = None,
    outcome: str = "success",
) -> None:
    """Persist safe account event identifiers in the caller's transaction."""
    AuditLog.objects.create(
        action=action,
        actor_id=actor_id,
        target_type="accounts.User",
        target_id=target_id,
        outcome=outcome,
        request_id=correlation_id_context.get() or "",
    )
