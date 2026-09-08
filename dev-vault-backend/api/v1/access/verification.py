import hashlib

from django.core.cache import cache
from django.db import InterfaceError, OperationalError
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from api.v1.helpers import StrictInput, validated
from apps.access.verification import verify_access
from apps.core.exceptions import DependencyUnavailableError
from apps.core.responses import error_response
from apps.credentials.hashing import InvalidCredential


class VerificationInput(StrictInput):
    service_id = serializers.UUIDField()
    environment = serializers.ChoiceField(choices=("test", "live"))
    audience = serializers.CharField(max_length=128)
    required_scopes = serializers.ListField(
        child=serializers.CharField(max_length=96), max_length=100
    )
    scope_mode = serializers.ChoiceField(choices=("all", "any"), default="all")
    units = serializers.IntegerField(min_value=1, max_value=1000000, default=1)
    method = serializers.ChoiceField(
        choices=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"), default="GET"
    )


class VerificationAbuseThrottle(BaseThrottle):
    """Separate bounded IP request budget. Edge deployments must rate-limit too."""

    def allow_request(self, request, view):
        address = request.META.get("REMOTE_ADDR", "unknown")
        key = "verify:abuse:" + hashlib.sha256(address.encode()).hexdigest()
        try:
            if cache.add(key, 1, timeout=60):
                return True
            return cache.incr(key) <= 1200
        except Exception as exc:
            raise DependencyUnavailableError(code="enforcement_unavailable") from exc

    def wait(self):
        return 60


class VerificationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [VerificationAbuseThrottle]

    def post(self, request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) > 140:
            raise InvalidCredential()
        integration = request.headers.get("X-DevVault-Service-Token", "")
        try:
            decision, status, replayed = verify_access(
                integration_secret=integration,
                raw_key=authorization[7:],
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                **validated(VerificationInput, request),
            )
        except (OperationalError, InterfaceError) as exc:
            raise DependencyUnavailableError(code="enforcement_unavailable") from exc
        if decision["allowed"]:
            response = Response({"data": {**decision, "replayed": replayed}}, status=status)
        else:
            response = error_response(
                code=decision["code"],
                message="The access request was denied.",
                status_code=status,
                details={**decision, "replayed": replayed},
                request=request,
            )
        response["Cache-Control"] = "no-store"
        if decision.get("retry_after"):
            response["Retry-After"] = str(decision["retry_after"])
        limits = decision.get("rate_limits") or []
        if limits:
            tightest = min(limits, key=lambda item: item["remaining"])
            response["X-RateLimit-Limit"] = str(tightest["limit"])
            response["X-RateLimit-Remaining"] = str(tightest["remaining"])
            response["X-RateLimit-Reset"] = str(tightest["reset_at"])
        return response
