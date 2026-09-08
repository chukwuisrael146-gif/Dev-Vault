import uuid

from django.db import models

from apps.core.models import ExportJobBase


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("Audit records are append-only")

    def delete(self):
        raise TypeError("Audit records are append-only")

    def bulk_update(self, objs, fields, batch_size=None):
        raise TypeError("Audit records are append-only")

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        if update_conflicts:
            raise TypeError("Audit records are append-only")
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=False,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )


class AuditLog(models.Model):
    """Account-stage audit facts; opaque references survive deletion of a user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=96)
    actor_id = models.UUIDField(null=True)
    target_type = models.CharField(max_length=64)
    target_id = models.UUIDField(null=True)
    outcome = models.CharField(max_length=32, default="success")
    request_id = models.CharField(max_length=128, blank=True)
    organization_id = models.UUIDField(null=True, db_index=True)
    changes = models.JSONField(default=dict, blank=True)
    actor_type = models.CharField(max_length=16, default="user")
    source_ip = models.GenericIPAddressField(null=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("target_id", "created_at"), name="audit_target_created_idx"),
        ]

    def __str__(self):
        return f"{self.action} {self.id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Audit records are append-only")
        # Prevent overwriting a known primary key with a new model instance.
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Audit records are append-only")


class AuditExport(ExportJobBase):
    pass
