from celery import shared_task
from django.utils import timezone

from apps.audit.models import AuditExport
from apps.audit.selectors import filtered_logs
from apps.core.exports import process_export


def rows_for(job):
    # Deliberately exclude arbitrary change metadata from CSV exports.
    return (
        filtered_logs(job.organization_id, job.filters)
        .order_by("created_at", "id")
        .values_list(
            "id",
            "created_at",
            "action",
            "actor_type",
            "actor_id",
            "target_type",
            "target_id",
            "outcome",
            "request_id",
        )
        .iterator(chunk_size=1000)
    )


@shared_task(ignore_result=True)
def process_audit_exports():
    ids = list(
        AuditExport.objects.filter(status="queued", expires_at__gt=timezone.now())
        .order_by("created_at")
        .values_list("id", flat=True)[:10]
    )
    return sum(
        process_export(
            AuditExport,
            identifier,
            (
                "event_id",
                "timestamp",
                "action",
                "actor_type",
                "actor_id",
                "target_type",
                "target_id",
                "outcome",
                "request_id",
            ),
            rows_for,
        )
        for identifier in ids
    )
