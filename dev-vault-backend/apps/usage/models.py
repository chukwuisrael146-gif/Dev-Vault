import uuid

from django.db import models

from apps.audit.models import AppendOnlyQuerySet
from apps.core.models import BaseModel, ExportJobBase


class UsageEvent(BaseModel):
    service = models.ForeignKey("projects.APIService", on_delete=models.PROTECT)
    key_id = models.UUIDField(null=True)
    family_id = models.UUIDField(null=True)
    method = models.CharField(max_length=7)
    outcome = models.CharField(max_length=32)
    units = models.PositiveBigIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    decision = models.JSONField()
    status_code = models.PositiveSmallIntegerField()
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("service", "created_at")),
            models.Index(fields=("key_id", "created_at")),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Usage events are immutable")
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Usage events are immutable")


class AggregationReceipt(BaseModel):
    event = models.OneToOneField(
        UsageEvent, on_delete=models.PROTECT, related_name="aggregation_receipt"
    )


class UsageAggregate(BaseModel):
    service = models.ForeignKey("projects.APIService", on_delete=models.PROTECT)
    hour = models.DateTimeField()
    key_id = models.UUIDField(default=uuid.UUID(int=0))
    method = models.CharField(max_length=7)
    outcome = models.CharField(max_length=32)
    requests = models.PositiveBigIntegerField(default=0)
    units = models.PositiveBigIntegerField(default=0)
    latency_ms_total = models.PositiveBigIntegerField(default=0)
    latency_ms_max = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-hour", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("service", "hour", "key_id", "method", "outcome"),
                name="usage_aggregate_unique",
            )
        ]


class QuotaReservation(BaseModel):
    event = models.ForeignKey(UsageEvent, on_delete=models.PROTECT, related_name="reservations")
    bucket = models.ForeignKey("access.QuotaBucket", on_delete=models.PROTECT)
    units = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("event", "bucket"), name="quota_event_bucket_unique")
        ]


class UsageExport(ExportJobBase):
    pass
