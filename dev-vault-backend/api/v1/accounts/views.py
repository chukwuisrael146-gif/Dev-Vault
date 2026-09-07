import secrets

from django.shortcuts import render
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.accounts.serializers import (
    EmailVerificationSerializer,
    LoginSerializer,
    RefreshTokenSerializer,
    RegistrationSerializer,
    ResendVerificationSerializer,
    TokenPairSerializer,
    UserSummarySerializer,
)
from api.v1.accounts.throttles import AccountRequestThrottle
from apps.accounts.auth_services import login_user, logout_session, refresh_session
from apps.accounts.services import request_email_verification, verify_email


class RegistrationView(APIView):
    """Create a new DevVault account."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AccountRequestThrottle]
    throttle_scope = "register"

    def post(self, request: Request) -> Response:
        input_serializer = RegistrationSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        user = input_serializer.save()
        output_serializer = UserSummarySerializer(user)

        return Response(
            {
                "data": {
                    "user": output_serializer.data,
                },
                "message": ("Account created successfully. Email verification is required."),
            },
            status=status.HTTP_201_CREATED,
        )


class EmailVerificationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AccountRequestThrottle]
    throttle_scope = "verify_email"

    def get(self, request: Request):
        nonce = secrets.token_urlsafe(24)
        response = render(request, "accounts/verify_email.html", {"nonce": nonce})
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        response["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        )
        return response

    def post(self, request: Request) -> Response:
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verify_email(token=serializer.validated_data["token"])
        return Response({"message": "Email verified successfully. You can now sign in."})


class ResendVerificationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AccountRequestThrottle]
    throttle_scope = "resend_verification"

    def post(self, request: Request) -> Response:
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_email_verification(email=serializer.validated_data["email"])
        return Response(
            {"message": "If this account needs verification, an email will be sent shortly."},
            status=status.HTTP_202_ACCEPTED,
        )


class SessionCommandView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AccountRequestThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        if response.status_code == 401:
            response["WWW-Authenticate"] = 'Bearer realm="devvault"'
        return response


class LoginView(SessionCommandView):
    throttle_scope = "login"

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, pair = login_user(
            **serializer.validated_data,
            source_ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response(
            {
                "data": {
                    **TokenPairSerializer(pair).data,
                    "token_type": "Bearer",
                    "user": UserSummarySerializer(user).data,
                }
            }
        )


class RefreshView(SessionCommandView):
    throttle_scope = "refresh"

    def post(self, request: Request) -> Response:
        serializer = RefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pair = refresh_session(**serializer.validated_data)
        return Response({"data": {**TokenPairSerializer(pair).data, "token_type": "Bearer"}})


class LogoutView(SessionCommandView):
    throttle_scope = "logout"

    def post(self, request: Request) -> Response:
        serializer = RefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        logout_session(**serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)
