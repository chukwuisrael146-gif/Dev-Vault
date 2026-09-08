from uuid import UUID

from django.db import transaction

from apps.usage.models import AggregationReceipt, UsageAggregate, UsageEvent


@transaction.atomic
def aggregate_event(event_id):
    event = UsageEvent.objects.select_for_update().filter(pk=event_id).first()
    if event is None or AggregationReceipt.objects.filter(event=event).exists():
        return False
    aggregate, _ = UsageAggregate.objects.get_or_create(
        service_id=event.service_id,
        hour=event.created_at.replace(minute=0, second=0, microsecond=0),
        key_id=event.key_id or UUID(int=0),
        method=event.method,
        outcome=event.outcome,
    )
    aggregate = UsageAggregate.objects.select_for_update().get(pk=aggregate.id)
    aggregate.requests += 1
    aggregate.units += event.units
    aggregate.latency_ms_total += event.latency_ms
    aggregate.latency_ms_max = max(aggregate.latency_ms_max, event.latency_ms)
    aggregate.save(
        update_fields=("requests", "units", "latency_ms_total", "latency_ms_max", "updated_at")
    )
    AggregationReceipt.objects.create(event=event)
    return True


def aggregate_pending(limit=500):
    identifiers = list(
        UsageEvent.objects.filter(aggregation_receipt__isnull=True)
        .order_by("created_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    return sum(aggregate_event(identifier) for identifier in identifiers)
