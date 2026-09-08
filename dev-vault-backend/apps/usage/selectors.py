from apps.organizations.selectors import get_organization
from apps.usage.models import UsageAggregate, UsageEvent


def events_for(*, actor, organization_id, filters):
    get_organization(actor=actor, organization_id=organization_id, capability="usage")
    return filtered_events(organization_id, filters)


def filtered_events(organization_id, filters):
    query = UsageEvent.objects.filter(
        service__environment__project__organization_id=organization_id,
        created_at__gte=filters["start"],
        created_at__lt=filters["end"],
    )
    for field in ("service_id", "key_id", "outcome", "method"):
        if filters.get(field):
            query = query.filter(**{field: filters[field]})
    return query


def aggregates_for(*, actor, organization_id, filters):
    get_organization(actor=actor, organization_id=organization_id, capability="usage")
    query = UsageAggregate.objects.filter(
        service__environment__project__organization_id=organization_id,
        hour__gte=filters["start"],
        hour__lt=filters["end"],
    )
    for field in ("service_id", "key_id", "outcome", "method"):
        if filters.get(field):
            query = query.filter(**{field: filters[field]})
    return query
