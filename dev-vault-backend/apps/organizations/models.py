from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Organization(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return self.name


class OrganizationMembership(BaseModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        DEVELOPER = "developer", "Developer"
        ANALYST = "analyst", "Analyst"
        BILLING = "billing", "Billing"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "user"), name="org_unique_membership"),
            models.CheckConstraint(
                condition=models.Q(role__in=["owner", "admin", "developer", "analyst", "billing"]),
                name="org_membership_valid_role",
            ),
        ]
        ordering = ("created_at", "id")

    def __str__(self):
        return f"Membership {self.id}"


class OrganizationInvitation(BaseModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="invitations"
    )
    email = models.EmailField()
    role = models.CharField(max_length=16, choices=OrganizationMembership.Role.choices)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    sent_at = models.DateTimeField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "email"),
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="org_one_open_invitation",
            )
        ]
        indexes = [models.Index(fields=("sent_at", "next_attempt_at"))]

    def __str__(self):
        return f"Invitation {self.id}"
