from rest_framework import serializers

from api.v1.helpers import StrictInput
from apps.credentials.models import APIKey, IntegrationCredential


class KeyOutput(serializers.ModelSerializer):
    service_id = serializers.UUIDField(read_only=True)
    successor_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = APIKey
        fields = (
            "id",
            "service_id",
            "name",
            "consumer_reference",
            "display_prefix",
            "last_four",
            "status",
            "expires_at",
            "revoked_at",
            "successor_id",
            "last_used_at",
            "created_at",
        )
        read_only_fields = fields


class IntegrationOutput(serializers.ModelSerializer):
    service_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = IntegrationCredential
        fields = ("id", "service_id", "name", "expires_at", "revoked_at", "created_at")
        read_only_fields = fields


class KeyInput(StrictInput):
    service_id = serializers.UUIDField()
    name = serializers.CharField(max_length=128)
    consumer_reference = serializers.CharField(max_length=128, required=False, allow_blank=True)
    expires_at = serializers.DateTimeField(required=False)
    permission_ids = serializers.ListField(
        child=serializers.UUIDField(), max_length=100, required=False
    )


class RevokeInput(StrictInput):
    confirm = serializers.BooleanField()
    reason = serializers.ChoiceField(
        choices=("revoked", "compromised", "retired"), default="revoked"
    )


class RotateInput(StrictInput):
    confirm = serializers.BooleanField()
    overlap_seconds = serializers.IntegerField(min_value=0, max_value=86400, default=0)


class IntegrationInput(StrictInput):
    name = serializers.CharField(max_length=128)
