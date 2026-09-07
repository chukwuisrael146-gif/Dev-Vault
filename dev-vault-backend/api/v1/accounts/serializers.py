from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.services import register_user


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=1024,
        style={"input_type": "password"},
    )
    password_confirmation = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=1024,
        style={"input_type": "password"},
    )

    def validate(self, attributes):
        if attributes["password"] != attributes["password_confirmation"]:
            raise serializers.ValidationError(
                {"password_confirmation": ["The passwords do not match."]}
            )
        return attributes

    def create(self, validated_data):
        try:
            return register_user(
                email=validated_data["email"],
                password=validated_data["password"],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc


class UserSummarySerializer(serializers.ModelSerializer):
    email_is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "status",
            "email_is_verified",
            "created_at",
        )
        read_only_fields = fields


class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, max_length=256, trim_whitespace=False)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=1024,
        style={"input_type": "password"},
    )


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(write_only=True, max_length=4096, trim_whitespace=False)


class TokenPairSerializer(serializers.Serializer):
    access_token = serializers.CharField(read_only=True)
    refresh_token = serializers.CharField(read_only=True)
    expires_in = serializers.IntegerField(read_only=True)
    refresh_expires_in = serializers.IntegerField(read_only=True)
