from django.db.models import Q

from apps.access.models import Permission, Policy
from apps.core.exceptions import NotFoundError
from apps.organizations.selectors import get_organization, organizations_for
from apps.projects.selectors import get_service


def permissions_for(*, actor, service_id):
    service, _ = get_service(actor=actor, service_id=service_id)
    return Permission.objects.filter(service=service)


def policies_for(*, actor, organization_id):
    organization, _ = get_organization(actor=actor, organization_id=organization_id)
    return Policy.objects.filter(organization=organization)


def get_policy(*, actor, policy_id, capability="read", lock=False):
    row = Policy.objects.filter(organization__in=organizations_for(actor), pk=policy_id).first()
    if row is None:
        raise NotFoundError()
    _, member = get_organization(
        actor=actor, organization_id=row.organization_id, capability=capability, lock=lock
    )
    if lock:
        row = Policy.objects.select_for_update().get(pk=row.id)
    return row, member


def applicable_policies(*, key, service):
    return (
        Policy.objects.filter(
            organization_id=service.environment.project.organization_id,
            environment_kind=service.environment.kind,
            is_active=True,
        )
        .filter(Q(project__isnull=True) | Q(project_id=service.environment.project_id))
        .filter(Q(service__isnull=True) | Q(service_id=service.id))
        .filter(Q(key_family_id__isnull=True) | Q(key_family_id=key.family_id))
        .order_by("id")
    )
