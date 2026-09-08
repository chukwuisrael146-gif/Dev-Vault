import secrets

from django.shortcuts import render
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.accounts.serializers import ResendVerificationSerializer, UserSummarySerializer
from api.v1.accounts.throttles import AccountRequestThrottle
from api.v1.accounts.views import SessionCommandView
from apps.accounts.profile_services import (
    change_password,
    request_password_reset,
    reset_password,
    update_profile,
)


class CurrentUserSerializer(UserSummarySerializer):
    class Meta(UserSummarySerializer.Meta):
        fields = (*UserSummarySerializer.Meta.fields, "first_name", "last_name")
        read_only_fields = fields


class ProfileInput(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, allow_blank=True)
    last_name = serializers.CharField(max_length=150, allow_blank=True)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["Only first_name and last_name may be changed here."]}
            )
        return super().to_internal_value(data)


class NewPasswordInput(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=1024)
    password_confirmation = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=1024
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError(
                {"password_confirmation": "The passwords do not match."}
            )
        attrs.pop("password_confirmation")
        return attrs


class PasswordChangeInput(NewPasswordInput):
    current_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=1024
    )


class PasswordResetInput(NewPasswordInput):
    token = serializers.CharField(write_only=True, max_length=256, trim_whitespace=False)


class CurrentUserView(APIView):
    def get(self, request):
        return Response(
            {"data": {"user": CurrentUserSerializer(request.user).data}},
            headers={"Cache-Control": "no-store"},
        )

    def patch(self, request):
        serializer = ProfileInput(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = update_profile(
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(
            {"data": {"user": CurrentUserSerializer(user).data}},
            headers={"Cache-Control": "no-store"},
        )


class PasswordChangeView(APIView):
    throttle_classes = [AccountRequestThrottle]
    throttle_scope = "password_change"

    def post(self, request):
        serializer = PasswordChangeInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_password(actor=request.user, **serializer.validated_data)
        return Response(
            {"message": "Password changed. Sign in again on all devices."},
            headers={"Cache-Control": "no-store"},
        )


class PasswordResetRequestView(SessionCommandView):
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(**serializer.validated_data)
        return Response(
            {"message": "If this account is eligible, a password reset email will be sent."},
            status=202,
        )


class PasswordResetConfirmView(SessionCommandView):
    throttle_scope = "password_reset_confirm"

    def get(self, request):
        nonce = secrets.token_urlsafe(24)
        response = render(request, "accounts/reset_password.html", {"nonce": nonce})
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        response["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        )
        return response

    def post(self, request):
        serializer = PasswordResetInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_password(**serializer.validated_data)
        return Response({"message": "Password reset successfully. Sign in with your new password."})
