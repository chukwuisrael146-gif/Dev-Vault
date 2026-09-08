from rest_framework import serializers

from api.v1.helpers import StrictInput
from apps.access.models import Permission, Policy, PolicyRevision


class PermissionOutput(serializers.ModelSerializer):
    service_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Permission
        fields = ("id", "service_id", "name", "description", "is_active", "created_at")
        read_only_fields = fields


class PermissionInput(StrictInput):
    name = serializers.CharField(max_length=96)
    description = serializers.CharField(max_length=256, allow_blank=True, default="")


class PermissionStatusInput(StrictInput):
    is_active = serializers.BooleanField()
    confirm = serializers.BooleanField()


class GrantInput(StrictInput):
    permission_ids = serializers.ListField(child=serializers.UUIDField(), max_length=100)
    confirm = serializers.BooleanField(default=False)


class PolicyOutput(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)
    project_id = serializers.UUIDField(read_only=True, allow_null=True)
    service_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Policy
        fields = (
            "id",
            "organization_id",
            "environment_kind",
            "project_id",
            "service_id",
            "key_family_id",
            "name",
            "algorithm",
            "dimension",
            "config",
            "version",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RevisionOutput(serializers.ModelSerializer):
    class Meta:
        model = PolicyRevision
        fields = ("id", "version", "snapshot", "created_at")
        read_only_fields = fields


class PolicyInput(StrictInput):
    name = serializers.CharField(max_length=128)
    environment_kind = serializers.ChoiceField(choices=("test", "live"))
    algorithm = serializers.ChoiceField(
        choices=("fixed_window", "token_bucket", "daily", "monthly")
    )
    dimension = serializers.ChoiceField(choices=("shared", "key"))
    config = serializers.JSONField()
    project_id = serializers.UUIDField(required=False)
    service_id = serializers.UUIDField(required=False)
    key_id = serializers.UUIDField(required=False)


class PolicyUpdate(StrictInput):
    expected_version = serializers.IntegerField(min_value=1)
    confirm = serializers.BooleanField()
    name = serializers.CharField(max_length=128, required=False)
    config = serializers.JSONField(required=False)
    is_active = serializers.BooleanField(required=False)


class QuotaAdjustmentInput(StrictInput):
    dimension_id = serializers.UUIDField(required=False)
    delta = serializers.IntegerField(min_value=-(10**12), max_value=10**12)
    reason = serializers.CharField(min_length=5, max_length=256)
    confirm = serializers.BooleanField()
