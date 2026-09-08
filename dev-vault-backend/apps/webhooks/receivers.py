from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.audit.models import AuditLog
from apps.usage.models import UsageEvent
from apps.webhooks.services import enqueue_event


@receiver(post_save, sender=AuditLog, dispatch_uid="webhooks.audit_event.v1")
def audit_event(sender, instance, created, **kwargs):
    if created and instance.organization_id:
        enqueue_event(
            organization_id=instance.organization_id,
            event_id=instance.id,
            event_type=instance.action,
            created_at=instance.created_at,
            data={
                "target_type": instance.target_type,
                "target_id": str(instance.target_id) if instance.target_id else None,
                "changes": instance.changes,
            },
        )


@receiver(post_save, sender=UsageEvent, dispatch_uid="webhooks.denied_usage.v1")
def usage_event(sender, instance, created, **kwargs):
    if created and instance.outcome in {"rate_limited", "quota_exceeded"}:
        enqueue_event(
            organization_id=instance.service.environment.project.organization_id,
            event_id=instance.id,
            event_type=f"access.{instance.outcome}",
            created_at=instance.created_at,
            data={
                "service_id": str(instance.service_id),
                "key_id": str(instance.key_id) if instance.key_id else None,
            },
        )
