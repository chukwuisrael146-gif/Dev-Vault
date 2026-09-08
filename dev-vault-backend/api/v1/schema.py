"""Explicit APIView contracts. Schema generation fails on unregistered operations."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import serializers

from api.v1 import reporting as report
from api.v1 import webhooks as hook
from api.v1.access import serializers as access
from api.v1.access.verification import VerificationInput
from api.v1.accounts import profile
from api.v1.accounts import serializers as account
from api.v1.credentials import serializers as credential
from api.v1.organizations import serializers as org
from api.v1.projects import serializers as project


class DashboardAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "api.v1.accounts.authentication.DashboardJWTAuthentication"
    name = "DashboardAccess"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Short-lived dashboard access JWT. Consumer API keys are not accepted.",
        }


class ErrorDetail(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField()
    request_id = serializers.CharField(allow_null=True)


class ErrorEnvelope(serializers.Serializer):
    error = ErrorDetail()


class MessageOutput(serializers.Serializer):
    message = serializers.CharField()


class LoginOutput(account.TokenPairSerializer):
    token_type = serializers.CharField()
    user = account.UserSummarySerializer()


class RefreshOutput(account.TokenPairSerializer):
    token_type = serializers.CharField()


class JobOutput(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=("queued", "ready", "failed"))
    row_count = serializers.IntegerField()
    failure_code = serializers.CharField(allow_null=True)
    expires_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class LimitOutput(serializers.Serializer):
    policy_id = serializers.UUIDField()
    limit = serializers.IntegerField()
    remaining = serializers.IntegerField()
    reset_at = serializers.IntegerField(help_text="UTC Unix timestamp in seconds")


class VerificationOutput(serializers.Serializer):
    allowed = serializers.BooleanField()
    code = serializers.CharField()
    key_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    environment = serializers.ChoiceField(choices=("test", "live"))
    audience = serializers.CharField()
    rate_limits = LimitOutput(many=True)
    quotas = LimitOutput(many=True)
    retry_after = serializers.IntegerField()
    replayed = serializers.BooleanField()


class SummaryOutput(serializers.Serializer):
    requests = serializers.IntegerField()
    units = serializers.IntegerField()
    mean_latency_ms = serializers.FloatField(allow_null=True)


class SeriesOutput(serializers.Serializer):
    hour = serializers.DateTimeField(help_text="UTC bucket start; midnight for daily granularity")
    requests = serializers.IntegerField()
    units = serializers.IntegerField()


class UsageOutput(serializers.Serializer):
    summary = SummaryOutput()
    series = SeriesOutput(many=True)
    granularity = serializers.ChoiceField(choices=("hour", "day"))
    aggregation_pending = serializers.IntegerField()
    source = serializers.CharField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()


class ImpactOutput(serializers.Serializer):
    affected_keys = serializers.IntegerField()


class GrantsOutput(serializers.Serializer):
    permission_ids = serializers.ListField(child=serializers.UUIDField())


class AdjustmentOutput(serializers.Serializer):
    id = serializers.UUIDField()
    delta = serializers.IntegerField()
    bucket_id = serializers.UUIDField()


INPUTS = {
    "RegistrationView": account.RegistrationSerializer,
    "EmailVerificationView": account.EmailVerificationSerializer,
    "ResendVerificationView": account.ResendVerificationSerializer,
    "LoginView": account.LoginSerializer,
    "RefreshView": account.RefreshTokenSerializer,
    "LogoutView": account.RefreshTokenSerializer,
    "CurrentUserView": profile.ProfileInput,
    "PasswordChangeView": profile.PasswordChangeInput,
    "PasswordResetRequestView": account.ResendVerificationSerializer,
    "PasswordResetConfirmView": profile.PasswordResetInput,
    "OrganizationsView": org.OrganizationInput,
    "OrganizationView": org.OrganizationUpdate,
    "ArchiveView": org.ConfirmationInput,
    "MemberRoleView": org.RoleInput,
    "MemberRemoveView": org.ConfirmationInput,
    "TransferView": org.TransferInput,
    "InvitationsView": org.InvitationInput,
    "InvitationAcceptView": org.InvitationAccept,
    "ProjectsView": project.ProjectInput,
    "ProjectView": project.ProjectUpdate,
    "ProjectArchiveView": org.ConfirmationInput,
    "ServicesView": project.ServiceInput,
    "ServiceStatusView": project.ServiceStatusInput,
    "KeysView": credential.KeyInput,
    "KeyRevokeView": credential.RevokeInput,
    "KeyRotateView": credential.RotateInput,
    "IntegrationsView": credential.IntegrationInput,
    "IntegrationRevokeView": org.ConfirmationInput,
    "PermissionsView": access.PermissionInput,
    "PermissionStatusView": access.PermissionStatusInput,
    "KeyPermissionsView": access.GrantInput,
    "PoliciesView": access.PolicyInput,
    "PolicyView": access.PolicyUpdate,
    "QuotaAdjustmentView": access.QuotaAdjustmentInput,
    "VerificationView": VerificationInput,
    "UsageExportsView": report.UsageFilters,
    "AuditExportsView": report.AuditFilters,
    "EndpointsView": hook.EndpointInput,
    "EndpointStatusView": hook.EndpointStatusInput,
    "EndpointSecretView": org.ConfirmationInput,
    "DeliveryRetryView": org.ConfirmationInput,
}
OUTPUTS = {
    "OrganizationsView": org.OrganizationOutput,
    "OrganizationView": org.OrganizationOutput,
    "ArchiveView": org.OrganizationOutput,
    "MembersView": org.MemberOutput,
    "MemberRoleView": org.MemberOutput,
    "InvitationAcceptView": org.MemberOutput,
    "InvitationsView": org.InvitationOutput,
    "ProjectsView": project.ProjectOutput,
    "ProjectView": project.ProjectOutput,
    "ProjectArchiveView": project.ProjectOutput,
    "EnvironmentsView": project.EnvironmentOutput,
    "ServicesView": project.ServiceOutput,
    "ServiceView": project.ServiceOutput,
    "ServiceStatusView": project.ServiceOutput,
    "KeysView": credential.KeyOutput,
    "KeyView": credential.KeyOutput,
    "KeyRevokeView": credential.KeyOutput,
    "KeyRotateView": credential.KeyOutput,
    "IntegrationsView": credential.IntegrationOutput,
    "PermissionsView": access.PermissionOutput,
    "PermissionStatusView": access.PermissionOutput,
    "PermissionImpactView": ImpactOutput,
    "KeyPermissionsView": access.PermissionOutput,
    "PoliciesView": access.PolicyOutput,
    "PolicyView": access.PolicyOutput,
    "RatePoliciesView": access.PolicyOutput,
    "QuotaPoliciesView": access.PolicyOutput,
    "PolicyRevisionsView": access.RevisionOutput,
    "QuotaAdjustmentView": AdjustmentOutput,
    "VerificationView": VerificationOutput,
    "UsageView": UsageOutput,
    "UsageEventsView": report.EventOutput,
    "AuditLogsView": report.AuditOutput,
    "UsageExportsView": JobOutput,
    "AuditExportsView": JobOutput,
    "UsageExportView": JobOutput,
    "AuditExportView": JobOutput,
    "EndpointsView": hook.EndpointOutput,
    "EndpointStatusView": hook.EndpointOutput,
    "EndpointSecretView": hook.EndpointOutput,
    "DeliveriesView": hook.DeliveryOutput,
    "DeliveryAttemptsView": hook.AttemptOutput,
    "DeliveryRetryView": hook.DeliveryOutput,
}
LISTS = {
    "OrganizationsView",
    "MembersView",
    "InvitationsView",
    "ProjectsView",
    "ServicesView",
    "KeysView",
    "IntegrationsView",
    "PermissionsView",
    "KeyPermissionsView",
    "PoliciesView",
    "RatePoliciesView",
    "QuotaPoliciesView",
    "PolicyRevisionsView",
    "UsageEventsView",
    "AuditLogsView",
    "UsageExportsView",
    "AuditExportsView",
    "EndpointsView",
    "DeliveriesView",
    "DeliveryAttemptsView",
}
CREATIONS = {
    "OrganizationsView",
    "ProjectsView",
    "ServicesView",
    "KeysView",
    "IntegrationsView",
    "PermissionsView",
    "PoliciesView",
    "QuotaAdjustmentView",
    "EndpointsView",
    "KeyRotateView",
}
IDEMPOTENT = CREATIONS | {
    "VerificationView",
    "UsageExportsView",
    "AuditExportsView",
    "EndpointSecretView",
    "DeliveryRetryView",
}
NO_CONTENT = {
    "LogoutView",
    "MemberRemoveView",
    "TransferView",
    "InvitationRevokeView",
    "IntegrationRevokeView",
}
MESSAGES = {
    "EmailVerificationView",
    "ResendVerificationView",
    "PasswordChangeView",
    "PasswordResetRequestView",
    "PasswordResetConfirmView",
}


def object_schema(properties, required=None):
    result = {"type": "object", "properties": properties}
    required = list(properties) if required is None else required
    if required:
        result["required"] = required
    return result


class DevVaultSchema(AutoSchema):
    def get_operation_id(self):
        return (
            self.method.lower()
            + "_"
            + self.path.strip("/")
            .replace("/", "_")
            .replace("{", "")
            .replace("}", "")
            .replace("-", "_")
        )

    def get_request_serializer(self):
        if self.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        return INPUTS.get(type(self.view).__name__)

    def _ref(self, serializer):
        return self.resolve_serializer(serializer(), "response").ref

    def get_response_serializers(self):
        name = type(self.view).__name__
        errors = {code: ErrorEnvelope for code in (400, 401, 403, 404, 409, 413, 429, 500, 503)}
        if self.path.startswith("/api/v1/health/"):
            return {
                200: object_schema({"status": {"type": "string"}}),
                503: object_schema({"status": {"type": "string"}}),
            }
        if self.method == "GET" and name in {"EmailVerificationView", "PasswordResetConfirmView"}:
            return {(200, "text/html"): OpenApiTypes.STR}
        if getattr(self.view, "download", False):
            return {(200, "text/csv"): OpenApiTypes.BINARY, **errors}
        if name in NO_CONTENT:
            return {204: None, **errors}
        if name in MESSAGES:
            return {
                202
                if name in {"ResendVerificationView", "PasswordResetRequestView"}
                else 200: MessageOutput,
                **errors,
            }
        if name == "RegistrationView":
            return {
                201: object_schema(
                    {
                        "data": object_schema({"user": self._ref(account.UserSummarySerializer)}),
                        "message": {"type": "string"},
                    }
                ),
                **errors,
            }
        if name in {"LoginView", "RefreshView"}:
            return {
                200: object_schema(
                    {"data": self._ref(LoginOutput if name == "LoginView" else RefreshOutput)}
                ),
                **errors,
            }
        if name == "CurrentUserView":
            return {
                200: object_schema(
                    {"data": object_schema({"user": self._ref(profile.CurrentUserSerializer)})}
                ),
                **errors,
            }
        serializer = OUTPUTS.get(name)
        if serializer is None:
            raise RuntimeError(f"Missing API response contract: {name} {self.method}")
        if name == "KeyPermissionsView" and self.method == "PUT":
            serializer = GrantsOutput
        item = self._ref(serializer)
        if self.method == "GET" and name in LISTS:
            return {
                200: object_schema(
                    {
                        "next": {"type": "string", "nullable": True},
                        "previous": {"type": "string", "nullable": True},
                        "results": {"type": "array", "items": item},
                    }
                ),
                **errors,
            }
        if name == "EnvironmentsView":
            item = {"type": "array", "items": item}
        output = object_schema({"data": item})
        if self.method == "POST" and name in {
            "KeysView",
            "KeyRotateView",
            "IntegrationsView",
            "EndpointsView",
            "EndpointSecretView",
        }:
            secret_item = {
                "allOf": [
                    item,
                    object_schema(
                        {
                            "secret": {
                                "type": "string",
                                "readOnly": True,
                                "description": (
                                    "One-time secret. Absent on an idempotent retry; "
                                    "never stored in a recoverable command response."
                                ),
                            }
                        },
                        required=[],
                    ),
                ]
            }
            if name == "EndpointsView":
                secret_item["allOf"].append(
                    object_schema({"delivery_enabled": {"type": "boolean"}})
                )
            created_output = object_schema({"data": secret_item})
        else:
            created_output = output
        if self.method == "POST" and name in CREATIONS:
            return {201: created_output, 200: output, **errors}
        if self.method == "POST" and name in {
            "UsageExportsView",
            "AuditExportsView",
            "DeliveryRetryView",
        }:
            return {202: output, 200: output, **errors}
        if name == "InvitationsView" and self.method == "POST":
            return {201: output, **errors}
        return {200: created_output, **errors}

    def get_override_parameters(self):
        name = type(self.view).__name__
        params = []
        if self.method == "POST" and name in IDEMPOTENT:
            params.append(
                OpenApiParameter(
                    "Idempotency-Key",
                    str,
                    OpenApiParameter.HEADER,
                    required=True,
                    description=(
                        "1–128 ASCII characters. Reuse only for the same logical "
                        "request and identical input."
                    ),
                )
            )
        if self.method == "GET" and name in LISTS:
            params.extend(
                [
                    OpenApiParameter("cursor", str),
                    OpenApiParameter("page_size", int, description="1–100, default 50"),
                ]
            )
        if self.method == "GET" and name in {"UsageView", "UsageEventsView", "AuditLogsView"}:
            filter_class = {
                "UsageView": report.UsageSummaryFilters,
                "UsageEventsView": report.UsageFilters,
                "AuditLogsView": report.AuditFilters,
            }[name]
            filters = filter_class()
            filters.fields["start"].required = False
            filters.fields["end"].required = False
            params.append(filters)
        if self.method == "GET" and name == "KeysView":
            params.extend(
                [
                    OpenApiParameter(
                        "status", str, enum=["active", "revoked", "expired", "rotated"]
                    ),
                    OpenApiParameter("search", str),
                ]
            )
        return params

    def get_auth(self):
        if type(self.view).__name__ == "VerificationView":
            return [{"ConsumerKey": [], "ServiceIntegration": []}]
        return super().get_auth()
