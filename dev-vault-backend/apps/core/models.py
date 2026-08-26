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
