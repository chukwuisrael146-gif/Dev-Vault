import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class APIKey(BaseModel):
    # Stable across rotations: limits must not reset when a secret changes.
    family_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    service = models.ForeignKey(
        "projects.APIService", on_delete=models.PROTECT, related_name="api_keys", editable=False
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False
    )
    name = models.CharField(max_length=128)
    consumer_reference = models.CharField(max_length=128, blank=True)
    verifier = models.CharField(max_length=64, editable=False)
    pepper_version = models.CharField(max_length=16, editable=False)
    display_prefix = models.CharField(max_length=32, editable=False)
    last_four = models.CharField(max_length=4, editable=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)
    revocation_reason = models.CharField(max_length=32, blank=True)
    successor = models.OneToOneField(
        "self", null=True, on_delete=models.PROTECT, related_name="predecessor", editable=False
    )
    last_used_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("service", "revoked_at", "expires_at")),
            models.Index(fields=("service", "last_used_at")),
        ]

    @property
    def status(self) -> str:
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= timezone.now():
            return "expired"
        return "rotated" if self.successor_id else "active"

    def __str__(self):
        return f"API key {self.id}"


class IntegrationCredential(BaseModel):
    """Server-to-server context proof, never a consumer key or dashboard JWT."""

    service = models.ForeignKey(
        "projects.APIService",
        on_delete=models.PROTECT,
        related_name="integration_credentials",
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False
    )
    name = models.CharField(max_length=128)
    verifier = models.CharField(max_length=64, editable=False)
    pepper_version = models.CharField(max_length=16, editable=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"Integration credential {self.id}"
