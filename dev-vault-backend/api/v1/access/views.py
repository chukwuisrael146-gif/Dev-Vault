from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.access.serializers import (
    GrantInput,
    PermissionInput,
    PermissionOutput,
    PermissionStatusInput,
    PolicyInput,
    PolicyOutput,
    PolicyUpdate,
    QuotaAdjustmentInput,
    RevisionOutput,
)
from api.v1.helpers import paginated, validated
from apps.access import selectors, services
from apps.access.models import Permission
from apps.credentials.selectors import get_key
from apps.projects.selectors import get_service


class PermissionsView(APIView):
    def get(self, request, service_id):
        return paginated(
            selectors.permissions_for(actor=request.user, service_id=service_id),
            PermissionOutput,
            request,
        )

    def post(self, request, service_id):
        row, created = services.create_permission(
            actor=request.user,
            service_id=service_id,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(PermissionInput, request),
        )
        return Response({"data": PermissionOutput(row).data}, status=201 if created else 200)


class PermissionImpactView(APIView):
    def get(self, request, service_id, permission_id):
        from apps.core.exceptions import NotFoundError

        get_service(actor=request.user, service_id=service_id, capability="policy")
        permission = (
            selectors.permissions_for(actor=request.user, service_id=service_id)
            .filter(pk=permission_id)
            .first()
        )
        if permission is None:
            raise NotFoundError()
        return Response({"data": {"affected_keys": permission.grants.count()}})


class PermissionStatusView(APIView):
    def post(self, request, service_id, permission_id):
        row = services.set_permission_status(
            actor=request.user,
            session=request.auth,
            service_id=service_id,
            permission_id=permission_id,
            **validated(PermissionStatusInput, request),
        )
        return Response({"data": PermissionOutput(row).data})


class KeyPermissionsView(APIView):
    def get(self, request, key_id):
        key, _ = get_key(actor=request.user, key_id=key_id)
        return paginated(Permission.objects.filter(grants__key=key), PermissionOutput, request)

    def put(self, request, key_id):
        key = services.assign_key_permissions(
            actor=request.user,
            session=request.auth,
            key_id=key_id,
            **validated(GrantInput, request),
        )
        return Response(
            {"data": {"permission_ids": list(key.grants.values_list("permission_id", flat=True))}}
        )


class PoliciesView(APIView):
    def get(self, request, organization_id):
        return paginated(
            selectors.policies_for(actor=request.user, organization_id=organization_id),
            PolicyOutput,
            request,
        )

    def post(self, request, organization_id):
        row, created = services.create_policy(
            actor=request.user,
            organization_id=organization_id,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(PolicyInput, request),
        )
        return Response({"data": PolicyOutput(row).data}, status=201 if created else 200)


class ServicePoliciesView(APIView):
    algorithms = ()

    def get(self, request, service_id):
        service, _ = get_service(actor=request.user, service_id=service_id)
        query = selectors.policies_for(
            actor=request.user, organization_id=service.environment.project.organization_id
        )
        return paginated(
            query.filter(service=service, algorithm__in=self.algorithms), PolicyOutput, request
        )


class RatePoliciesView(ServicePoliciesView):
    algorithms = ("fixed_window", "token_bucket")


class QuotaPoliciesView(ServicePoliciesView):
    algorithms = ("daily", "monthly")


class PolicyView(APIView):
    def get(self, request, policy_id):
        policy, _ = selectors.get_policy(actor=request.user, policy_id=policy_id)
        return Response({"data": PolicyOutput(policy).data})

    def patch(self, request, policy_id):
        policy = services.update_policy(
            actor=request.user,
            session=request.auth,
            policy_id=policy_id,
            **validated(PolicyUpdate, request),
        )
        return Response({"data": PolicyOutput(policy).data})


class PolicyRevisionsView(APIView):
    def get(self, request, policy_id):
        policy, _ = selectors.get_policy(actor=request.user, policy_id=policy_id)
        return paginated(policy.revisions.all(), RevisionOutput, request)


class QuotaAdjustmentView(APIView):
    def post(self, request, policy_id):
        from apps.access.quotas import adjust_quota

        row, created = adjust_quota(
            actor=request.user,
            session=request.auth,
            policy_id=policy_id,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(QuotaAdjustmentInput, request),
        )
        return Response(
            {"data": {"id": str(row.id), "delta": row.delta, "bucket_id": str(row.bucket_id)}},
            status=201 if created else 200,
        )
