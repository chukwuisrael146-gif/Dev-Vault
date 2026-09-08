from celery import shared_task
from django.utils import timezone

from apps.core.exports import process_export
from apps.usage.models import UsageExport
from apps.usage.selectors import filtered_events


def rows_for(job):
    return (
        filtered_events(job.organization_id, job.filters)
        .order_by("created_at", "id")
        .values_list(
            "id", "created_at", "service_id", "key_id", "method", "outcome", "units", "latency_ms"
        )
        .iterator(chunk_size=1000)
    )


@shared_task(ignore_result=True)
def process_usage_exports():
    ids = list(
        UsageExport.objects.filter(status="queued", expires_at__gt=timezone.now())
        .order_by("created_at")
        .values_list("id", flat=True)[:10]
    )
    return sum(
        process_export(
            UsageExport,
            identifier,
            (
                "event_id",
                "timestamp",
                "service_id",
                "key_id",
                "method",
                "outcome",
                "units",
                "latency_ms",
            ),
            rows_for,
        )
        for identifier in ids
    )
