from django.db import models

from apps.core.models import BaseModel


class WebhookEndpoint(BaseModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    url = models.URLField(max_length=1024)
    event_types = models.JSONField()
    encrypted_secret = models.TextField(editable=False)
    is_active = models.BooleanField(default=True)
    secret_version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"Webhook endpoint {self.id}"


class WebhookDelivery(BaseModel):
    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.PROTECT, related_name="deliveries"
    )
    event_id = models.UUIDField()
    event_type = models.CharField(max_length=96)
    payload = models.JSONField()
    status = models.CharField(max_length=12, default="pending")
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    last_status_code = models.PositiveSmallIntegerField(null=True)
    last_error_code = models.CharField(max_length=32, blank=True)
    delivered_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "event_id"), name="webhook_endpoint_event_unique"
            )
        ]
        indexes = [models.Index(fields=("status", "next_attempt_at"))]


class DeliveryAttempt(BaseModel):
    delivery = models.ForeignKey(WebhookDelivery, on_delete=models.PROTECT, related_name="history")
    number = models.PositiveSmallIntegerField()
    status_code = models.PositiveSmallIntegerField(null=True)
    error_code = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("delivery", "number"), name="webhook_attempt_number_unique"
            )
        ]
