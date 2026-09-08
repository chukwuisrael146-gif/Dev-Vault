import logging

from apps.audit.services import record_event
from apps.core.responses import api_exception_handler as core_handler
from apps.organizations.selectors import organizations_for

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    response = core_handler(exc, context)
    request = context.get("request")
    actor = getattr(request, "user", None)
    if response.status_code in {403, 404} and getattr(actor, "is_authenticated", False):
        match = getattr(request, "resolver_match", None)
        organization_id = getattr(match, "kwargs", {}).get("organization_id")
        # Do not attach cross-tenant probing to another tenant's visible audit stream.
        if organization_id and not organizations_for(actor).filter(pk=organization_id).exists():
            organization_id = None
        try:
            record_event(
                action="authorization.denied",
                actor_id=actor.id,
                organization_id=organization_id,
                target_type="api.Endpoint",
                target_id=None,
                outcome="denied",
                changes={
                    "route": getattr(match, "route", "unresolved"),
                    "status_code": response.status_code,
                },
            )
        except Exception:
            logger.exception(
                "Authorization denial audit persistence failed",
                extra={"outcome": "audit_unavailable"},
            )
    response["Cache-Control"] = "no-store"
    return response
