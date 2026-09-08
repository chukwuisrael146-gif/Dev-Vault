from apps.audit.models import AuditLog
from apps.organizations.selectors import get_organization


def filtered_logs(organization_id, filters):
    query = AuditLog.objects.filter(
        organization_id=organization_id,
        created_at__gte=filters["start"],
        created_at__lt=filters["end"],
    )
    for field in ("action", "actor_id", "target_id", "outcome"):
        if filters.get(field):
            query = query.filter(**{field: filters[field]})
    return query


def logs_for(*, actor, organization_id, filters):
    get_organization(actor=actor, organization_id=organization_id, capability="audit")
    return filtered_logs(organization_id, filters)
