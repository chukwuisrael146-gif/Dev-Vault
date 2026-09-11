import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    """Abstract model that gives public resources an opaque UUID identifier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Abstract UTC-aware creation and modification timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel):
    """Common persistence primitive for ordinary mutable domain records."""

    class Meta:
        abstract = True


class ExportJobBase(BaseModel):
    """Reusable job state, with domain-specific concrete owners and query builders."""

    organization_id = models.UUIDField(db_index=True)
    actor_id = models.UUIDField()
    filters = models.JSONField()
    status = models.CharField(max_length=12, default="queued")
    row_count = models.PositiveIntegerField(default=0)
    failure_code = models.CharField(max_length=32, blank=True)
    expires_at = models.DateTimeField()
    storage_backend = models.CharField(max_length=8, default="local", choices=(("local", "Local"), ("s3", "S3")))

    class Meta:
        abstract = True
        ordering = ("-created_at", "-id")


class IdempotencyRecord(BaseModel):
    """Opaque command result reference, never a cached credential-bearing response."""

    actor_id = models.UUIDField()
    scope = models.CharField(max_length=160)
    key_hash = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    resource_id = models.UUIDField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("actor_id", "scope", "key_hash"),
                name="core_command_idempotency_unique",
            )
        ]

    def __str__(self):
        return f"Command {self.id}"
