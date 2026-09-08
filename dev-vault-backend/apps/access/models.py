from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Permission(BaseModel):
    service = models.ForeignKey("projects.APIService", on_delete=models.PROTECT, editable=False)
    name = models.CharField(max_length=96, editable=False)
    description = models.CharField(max_length=256, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("service", "name"), name="permission_service_name")
        ]

    def __str__(self):
        return self.name


class APIKeyPermission(BaseModel):
    key = models.ForeignKey("credentials.APIKey", on_delete=models.PROTECT, related_name="grants")
    permission = models.ForeignKey(Permission, on_delete=models.PROTECT, related_name="grants")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("key", "permission"), name="key_permission_unique")
        ]


class Policy(BaseModel):
    """Stable enforcement identity; every configuration change has an immutable revision.

    All applicable policies constrain a decision (most restrictive wins). Targets
    are immutable and remain separate for test/live even at organization level.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, editable=False
    )
    environment_kind = models.CharField(
        max_length=4, choices=(("test", "Test"), ("live", "Live")), editable=False
    )
    project = models.ForeignKey(
        "projects.Project", null=True, on_delete=models.PROTECT, editable=False
    )
    service = models.ForeignKey(
        "projects.APIService", null=True, on_delete=models.PROTECT, editable=False
    )
    key_family_id = models.UUIDField(null=True, editable=False)
    name = models.CharField(max_length=128)
    algorithm = models.CharField(
        max_length=16,
        choices=[(x, x) for x in ("fixed_window", "token_bucket", "daily", "monthly")],
        editable=False,
    )
    dimension = models.CharField(
        max_length=8, choices=(("shared", "Shared"), ("key", "Key family")), editable=False
    )
    config = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("organization", "environment_kind", "is_active"))]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(environment_kind__in=("test", "live")),
                name="policy_valid_environment",
            ),
            models.CheckConstraint(
                condition=models.Q(dimension__in=("shared", "key")), name="policy_valid_dimension"
            ),
            models.CheckConstraint(
                condition=models.Q(key_family_id__isnull=True) | models.Q(service__isnull=False),
                name="key_policy_has_service",
            ),
            models.CheckConstraint(
                condition=models.Q(service__isnull=True) | models.Q(project__isnull=False),
                name="service_policy_has_project",
            ),
        ]

    def __str__(self):
        return f"Policy {self.id} v{self.version}"


class PolicyRevision(BaseModel):
    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="revisions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("policy", "version"), name="policy_revision_unique")
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Policy revisions are immutable")
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)


class QuotaBucket(BaseModel):
    policy = models.ForeignKey(Policy, on_delete=models.PROTECT)
    dimension_id = models.UUIDField()
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    used = models.PositiveBigIntegerField(default=0)
    adjustment = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("policy", "dimension_id", "period_start"), name="quota_bucket_unique"
            )
        ]


class QuotaAdjustment(BaseModel):
    bucket = models.ForeignKey(QuotaBucket, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    delta = models.BigIntegerField()
    reason = models.CharField(max_length=256)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Quota adjustments are immutable")
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)


class QuotaNotice(BaseModel):
    bucket = models.ForeignKey(QuotaBucket, on_delete=models.PROTECT)
    threshold = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("bucket", "threshold"), name="quota_notice_unique")
        ]
