from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Project(BaseModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="projects",
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False
    )
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=64)
    archived_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "slug"), name="project_org_slug_unique")
        ]
        ordering = ("-created_at", "-id")

    def __str__(self):
        return self.name


class Environment(BaseModel):
    class Kind(models.TextChoices):
        TEST = "test", "Test"
        LIVE = "live", "Live"

    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="environments", editable=False
    )
    kind = models.CharField(max_length=8, choices=Kind.choices, editable=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("project", "kind"), name="project_environment_unique"),
            models.CheckConstraint(
                condition=models.Q(kind__in=("test", "live")), name="environment_canonical_kind"
            ),
        ]
        ordering = ("kind",)

    def __str__(self):
        return f"{self.kind} {self.id}"


class APIService(BaseModel):
    environment = models.ForeignKey(
        Environment, on_delete=models.PROTECT, related_name="services", editable=False
    )
    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=64)
    audience = models.CharField(max_length=128, editable=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("environment", "slug"), name="service_environment_slug_unique"
            ),
            models.UniqueConstraint(
                fields=("environment", "audience"), name="service_environment_audience_unique"
            ),
        ]
        ordering = ("-created_at", "-id")

    def __str__(self):
        return self.name
