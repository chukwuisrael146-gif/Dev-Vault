from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.credentials.serializers import (
    IntegrationInput,
    IntegrationOutput,
    KeyInput,
    KeyOutput,
    RevokeInput,
    RotateInput,
)
from api.v1.helpers import paginated, validated
from api.v1.organizations.serializers import ConfirmationInput
from apps.core.exceptions import NotFoundError
from apps.credentials import selectors, services
from apps.projects.selectors import get_environment, get_service


def issued_response(issued, serializer):
    data = dict(serializer(issued.resource).data)
    # A retry returns metadata only. Recovering a lost secret requires rotation.
    if issued.raw_value is not None:
        data["secret"] = issued.raw_value
    return Response(
        {"data": data}, status=201 if issued.created else 200, headers={"Cache-Control": "no-store"}
    )


class KeysView(APIView):
    def get(self, request, environment_id):
        return paginated(
            selectors.keys_for(
                actor=request.user,
                environment_id=environment_id,
                status=request.query_params.get("status"),
                search=request.query_params.get("search"),
            ),
            KeyOutput,
            request,
        )

    def post(self, request, environment_id):
        values = validated(KeyInput, request)
        get_environment(actor=request.user, environment_id=environment_id)
        service, _ = get_service(actor=request.user, service_id=values["service_id"])
        if service.environment_id != environment_id:
            raise NotFoundError()
        return issued_response(
            services.issue_key(
                actor=request.user,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                **values,
            ),
            KeyOutput,
        )


class KeyView(APIView):
    def get(self, request, key_id):
        key, _ = selectors.get_key(actor=request.user, key_id=key_id)
        return Response({"data": KeyOutput(key).data})


class KeyRevokeView(APIView):
    def post(self, request, key_id):
        key = services.revoke_key(
            actor=request.user,
            session=request.auth,
            key_id=key_id,
            **validated(RevokeInput, request),
        )
        return Response({"data": KeyOutput(key).data})


class KeyRotateView(APIView):
    def post(self, request, key_id):
        return issued_response(
            services.rotate_key(
                actor=request.user,
                session=request.auth,
                key_id=key_id,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                **validated(RotateInput, request),
            ),
            KeyOutput,
        )


class IntegrationsView(APIView):
    def get(self, request, service_id):
        return paginated(
            selectors.integrations_for(actor=request.user, service_id=service_id),
            IntegrationOutput,
            request,
        )

    def post(self, request, service_id):
        return issued_response(
            services.issue_integration_credential(
                actor=request.user,
                service_id=service_id,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                **validated(IntegrationInput, request),
            ),
            IntegrationOutput,
        )


class IntegrationRevokeView(APIView):
    def post(self, request, service_id, credential_id):
        services.revoke_integration_credential(
            actor=request.user,
            session=request.auth,
            service_id=service_id,
            credential_id=credential_id,
            **validated(ConfirmationInput, request),
        )
        return Response(status=204)
