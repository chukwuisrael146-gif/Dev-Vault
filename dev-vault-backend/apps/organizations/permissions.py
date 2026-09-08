"""Explicit organization capability matrix; unknown capabilities deny by default."""

from apps.core.exceptions import ForbiddenError

CAPABILITIES = {
    "owner": frozenset(
        {
            "read",
            "team",
            "ownership",
            "organization",
            "project",
            "key",
            "live_key",
            "policy",
            "usage",
            "audit",
            "webhook",
            "quota_adjust",
        }
    ),
    "admin": frozenset(
        {
            "read",
            "team",
            "project",
            "key",
            "live_key",
            "policy",
            "usage",
            "audit",
            "webhook",
            "quota_adjust",
        }
    ),
    "developer": frozenset({"read", "project", "key", "policy", "usage"}),
    "analyst": frozenset({"read", "usage", "audit"}),
    "billing": frozenset({"read", "usage", "quota_adjust"}),
}


def require_capability(role: str, capability: str) -> None:
    if capability not in CAPABILITIES.get(role, frozenset()):
        raise ForbiddenError()
