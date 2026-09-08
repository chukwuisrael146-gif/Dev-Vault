from rest_framework import serializers

from apps.organizations.models import Organization, OrganizationInvitation, OrganizationMembership


class OrganizationOutput(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "status", "created_at", "updated_at")
        read_only_fields = fields


class OrganizationInput(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    slug = serializers.RegexField(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)


class OrganizationUpdate(serializers.Serializer):
    name = serializers.CharField(max_length=128)


class ConfirmationInput(serializers.Serializer):
    confirm = serializers.BooleanField()


class MemberOutput(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ("id", "organization_id", "user_id", "email", "role", "is_active", "created_at")
        read_only_fields = fields


class RoleInput(serializers.Serializer):
    role = serializers.ChoiceField(choices=OrganizationMembership.Role.choices)


class TransferInput(ConfirmationInput):
    membership_id = serializers.UUIDField()


class InvitationInput(RoleInput):
    email = serializers.EmailField(max_length=254)


class InvitationOutput(serializers.ModelSerializer):
    class Meta:
        model = OrganizationInvitation
        fields = (
            "id",
            "organization_id",
            "email",
            "role",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "created_at",
        )
        read_only_fields = fields


class InvitationAccept(serializers.Serializer):
    token = serializers.CharField(write_only=True, max_length=256, trim_whitespace=False)
