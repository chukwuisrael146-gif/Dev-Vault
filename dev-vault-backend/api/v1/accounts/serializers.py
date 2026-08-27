from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.services import register_user


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    password_confirmation = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "pasword"},
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
            raise serializers.ValidationError(
                {"password": list(exc.messages)}
            ) from exc
            
class UserSummarySerializer(serializers.ModelSerializer):
    email_is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'status',
            'email_is_verified',
            'created_at',
        )
        read_only_fields = fields