import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.accounts.managers import UserManager
from apps.core.models import BaseModel


class User(AbstractUser, BaseModel):
    """A human idntity that can access the DevVault control plane."""

    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Pending Verification"
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"

    username = None
    email = models.EmailField(unique=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ("email",)
        verbose_name = "user"
        verbose_name_plural = "users"

    @property
    def email_is_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def can_authenticate(self) -> bool:
        return self.is_active and self.status == self.Status.ACTIVE

    def clean(self) -> None:
        super().clean()
        self.email = UserManager.normalize_email_address(self.email)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = UserManager.normalize_email_address(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email


class RefreshTokenSession(BaseModel):
    """A revocable server-side record for one dashboard login session."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_token_sessions",
    )
    token_jti = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    credential_hash = models.CharField(max_length=64, blank=True, default="", editable=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("user", "revoked_at"),
                name="acct_session_user_rev_idx",
            ),
            models.Index(
                fields=("expires_at",),
                name="acct_session_exp_idx",
            ),
        ]

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_usable(self) -> bool:
        return not self.is_revoked and not self.is_expired

    def __str__(self) -> str:
        return f"Session {self.id} for user {self.user_id}"


class EmailVerificationToken(BaseModel):
    """Single-use verification reference and durable pending-email record.

    The signed bearer token is generated for delivery, never stored here.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    email = models.EmailField()
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivery_attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=("user", "created_at"), name="acct_verify_user_created_idx"),
            models.Index(fields=("sent_at", "next_attempt_at"), name="acct_verify_delivery_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(consumed_at__isnull=True, invalidated_at__isnull=True),
                name="acct_one_open_verification",
            ),
        ]

    def __str__(self) -> str:
        return f"Email verification {self.id}"
