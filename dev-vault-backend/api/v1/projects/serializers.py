from rest_framework import serializers

from api.v1.helpers import StrictInput
from apps.projects.models import APIService, Environment, Project


class ProjectInput(StrictInput):
    name = serializers.CharField(max_length=128)
    slug = serializers.RegexField(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)


class ProjectUpdate(StrictInput):
    name = serializers.CharField(max_length=128)


class ServiceInput(ProjectInput):
    audience = serializers.RegexField(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}$", max_length=128)


class ServiceStatusInput(StrictInput):
    is_active = serializers.BooleanField()
    confirm = serializers.BooleanField()


class ProjectOutput(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = (
            "id",
            "organization_id",
            "name",
            "slug",
            "archived_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class EnvironmentOutput(serializers.ModelSerializer):
    class Meta:
        model = Environment
        fields = ("id", "project_id", "kind", "is_active", "created_at")
        read_only_fields = fields


class ServiceOutput(serializers.ModelSerializer):
    class Meta:
        model = APIService
        fields = (
            "id",
            "environment_id",
            "name",
            "slug",
            "audience",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
