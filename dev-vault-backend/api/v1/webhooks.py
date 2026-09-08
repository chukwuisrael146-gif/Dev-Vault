from django.conf import settings
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.helpers import StrictInput, paginated, validated
from api.v1.organizations.serializers import ConfirmationInput
from apps.core.exceptions import NotFoundError
from apps.organizations.selectors import get_organization
from apps.webhooks import services
from apps.webhooks.models import DeliveryAttempt, WebhookDelivery, WebhookEndpoint


class EndpointOutput(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = ("id", "url", "event_types", "is_active", "secret_version", "created_at")
        read_only_fields = fields


class EndpointInput(StrictInput):
    url = serializers.CharField(max_length=1024)
    event_types = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(services.EVENT_TYPES)),
        min_length=1,
        max_length=len(services.EVENT_TYPES),
    )


class EndpointStatusInput(StrictInput):
    is_active = serializers.BooleanField()
    confirm = serializers.BooleanField()


class DeliveryOutput(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = (
            "id",
            "event_id",
            "event_type",
            "status",
            "attempts",
            "next_attempt_at",
            "last_status_code",
            "last_error_code",
            "delivered_at",
            "created_at",
        )
        read_only_fields = fields


class AttemptOutput(serializers.ModelSerializer):
    class Meta:
        model = DeliveryAttempt
        fields = ("id", "number", "status_code", "error_code", "created_at")
        read_only_fields = fields


class EndpointsView(APIView):
    def get(self, request, organization_id):
        get_organization(actor=request.user, organization_id=organization_id, capability="webhook")
        return paginated(
            WebhookEndpoint.objects.filter(organization_id=organization_id), EndpointOutput, request
        )

    def post(self, request, organization_id):
        row, secret, created = services.create_endpoint(
            actor=request.user,
            organization_id=organization_id,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(EndpointInput, request),
        )
        data = {**EndpointOutput(row).data, "delivery_enabled": settings.WEBHOOK_DELIVERY_ENABLED}
        if secret:
            data["secret"] = secret
        return Response(
            {"data": data}, status=201 if created else 200, headers={"Cache-Control": "no-store"}
        )


class EndpointStatusView(APIView):
    def post(self, request, organization_id, endpoint_id):
        row = services.set_endpoint_status(
            actor=request.user,
            session=request.auth,
            organization_id=organization_id,
            endpoint_id=endpoint_id,
            **validated(EndpointStatusInput, request),
        )
        return Response({"data": EndpointOutput(row).data})


class EndpointSecretView(APIView):
    def post(self, request, organization_id, endpoint_id):
        row, secret = services.rotate_secret(
            actor=request.user,
            session=request.auth,
            organization_id=organization_id,
            endpoint_id=endpoint_id,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(ConfirmationInput, request),
        )
        data = dict(EndpointOutput(row).data)
        if secret:
            data["secret"] = secret
        return Response({"data": data}, headers={"Cache-Control": "no-store"})


class DeliveriesView(APIView):
    def get(self, request, organization_id, endpoint_id):
        row = services.endpoint_for(
            actor=request.user, organization_id=organization_id, endpoint_id=endpoint_id
        )
        return paginated(row.deliveries.all(), DeliveryOutput, request)


class DeliveryAttemptsView(APIView):
    def get(self, request, organization_id, endpoint_id, delivery_id):
        endpoint = services.endpoint_for(
            actor=request.user, organization_id=organization_id, endpoint_id=endpoint_id
        )
        row = endpoint.deliveries.filter(pk=delivery_id).first()
        if row is None:
            raise NotFoundError()
        return paginated(row.history.all(), AttemptOutput, request)


class DeliveryRetryView(APIView):
    def post(self, request, organization_id, endpoint_id, delivery_id):
        row = services.retry_delivery(
            actor=request.user,
            session=request.auth,
            organization_id=organization_id,
            endpoint_id=endpoint_id,
            delivery_id=delivery_id,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(ConfirmationInput, request),
        )
        return Response({"data": DeliveryOutput(row).data}, status=202)
