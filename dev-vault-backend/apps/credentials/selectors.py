from django.utils import timezone

from apps.core.exceptions import DomainError, NotFoundError
from apps.credentials.models import APIKey, IntegrationCredential
from apps.organizations.selectors import organizations_for
from apps.projects.selectors import get_environment, get_service


def keys_for(*, actor, environment_id, status=None, search=None):
    environment, _ = get_environment(actor=actor, environment_id=environment_id)
    query = APIKey.objects.filter(service__environment=environment).select_related(
        "service__environment"
    )
    if status == "revoked":
        query = query.filter(revoked_at__isnull=False)
    elif status == "expired":
        query = query.filter(revoked_at__isnull=True, expires_at__lte=timezone.now())
    elif status == "active":
        query = query.filter(
            revoked_at__isnull=True, expires_at__gt=timezone.now(), successor__isnull=True
        )
    elif status == "rotated":
        query = query.filter(
            revoked_at__isnull=True, expires_at__gt=timezone.now(), successor__isnull=False
        )
    elif status:
        raise DomainError(code="validation_error", message="Unknown key status filter.")
    if search:
        from django.db.models import Q

        if len(search) > 128:
            raise DomainError(
                code="validation_error", message="Search must be at most 128 characters."
            )
        query = query.filter(Q(name__icontains=search) | Q(display_prefix__istartswith=search))
    return query


def get_key(*, actor, key_id, capability="read", active_parent=False, lock=False):
    key = APIKey.objects.filter(
        service__environment__project__organization__in=organizations_for(actor), pk=key_id
    ).first()
    if key is None:
        raise NotFoundError()
    _, member = get_service(
        actor=actor,
        service_id=key.service_id,
        capability=capability,
        active=active_parent,
        lock=lock,
    )
    if lock:
        key = APIKey.objects.select_for_update().get(pk=key.id)
    return key, member


def integrations_for(*, actor, service_id):
    service, _ = get_service(actor=actor, service_id=service_id, capability="key")
    return IntegrationCredential.objects.filter(service=service)
