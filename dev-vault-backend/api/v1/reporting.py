from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDay, TruncHour
from django.http import FileResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.helpers import StrictInput, paginated, validated
from apps.audit.models import AuditExport, AuditLog
from apps.audit.selectors import logs_for
from apps.audit.services import record_event
from apps.core.exceptions import ConflictError, NotFoundError
from apps.core.exports import export_path
from apps.core.idempotency import creation_command, remember_created
from apps.organizations.selectors import get_organization
from apps.usage.models import UsageEvent, UsageExport
from apps.usage.selectors import events_for


class RangeInput(StrictInput):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    outcome = serializers.CharField(max_length=32, required=False)

    def validate(self, attrs):
        if not attrs["start"] < attrs["end"] or attrs["end"] - attrs["start"] > timedelta(days=93):
            raise serializers.ValidationError({"end": ["Use a positive range of at most 93 days."]})
        if attrs["end"] > timezone.now() + timedelta(minutes=1):
            raise serializers.ValidationError({"end": ["The range cannot end in the future."]})
        return attrs


class UsageFilters(RangeInput):
    service_id = serializers.UUIDField(required=False)
    key_id = serializers.UUIDField(required=False)
    method = serializers.ChoiceField(
        choices=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"), required=False
    )


class AuditFilters(RangeInput):
    action = serializers.RegexField(r"^[a-z][a-z0-9_.]{0,95}$", required=False)
    actor_id = serializers.UUIDField(required=False)
    target_id = serializers.UUIDField(required=False)


class UsageSummaryFilters(UsageFilters):
    granularity = serializers.ChoiceField(choices=("hour", "day"), default="hour")


def query_filters(request, serializer):
    now = timezone.now()
    data = {
        key: value
        for key, value in request.query_params.items()
        if key not in {"cursor", "page_size"}
    }
    data.setdefault("start", now - timedelta(days=7))
    data.setdefault("end", now)
    values = serializer(data=data)
    values.is_valid(raise_exception=True)
    return values.validated_data


class EventOutput(serializers.ModelSerializer):
    service_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = UsageEvent
        fields = (
            "id",
            "created_at",
            "service_id",
            "key_id",
            "method",
            "outcome",
            "units",
            "latency_ms",
            "status_code",
        )
        read_only_fields = fields


class AuditOutput(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = (
            "id",
            "created_at",
            "action",
            "actor_type",
            "actor_id",
            "target_type",
            "target_id",
            "outcome",
            "request_id",
            "changes",
        )
        read_only_fields = fields


class UsageView(APIView):
    def get(self, request, organization_id):
        filters = query_filters(request, UsageSummaryFilters)
        query = events_for(actor=request.user, organization_id=organization_id, filters=filters)
        # Exact selected range from durable facts; hourly series has at most 2233 rows.
        summary = query.aggregate(
            requests=Count("id"), units=Sum("units", default=0), mean_latency_ms=Avg("latency_ms")
        )
        truncate = TruncDay if filters["granularity"] == "day" else TruncHour
        series = list(
            query.annotate(hour=truncate("created_at"))
            .values("hour")
            .annotate(requests=Count("id"), units=Sum("units"))
            .order_by("hour")
        )
        return Response(
            {
                "data": {
                    "summary": summary,
                    "series": series,
                    "granularity": filters["granularity"],
                    "aggregation_pending": query.filter(aggregation_receipt__isnull=True).count(),
                    "source": "durable_events",
                    "start": filters["start"],
                    "end": filters["end"],
                }
            }
        )


class UsageEventsView(APIView):
    def get(self, request, organization_id):
        return paginated(
            events_for(
                actor=request.user,
                organization_id=organization_id,
                filters=query_filters(request, UsageFilters),
            ),
            EventOutput,
            request,
        )


class AuditLogsView(APIView):
    def get(self, request, organization_id):
        return paginated(
            logs_for(
                actor=request.user,
                organization_id=organization_id,
                filters=query_filters(request, AuditFilters),
            ),
            AuditOutput,
            request,
        )


def job_output(job):
    return {
        "id": str(job.id),
        "status": job.status,
        "row_count": job.row_count,
        "failure_code": job.failure_code or None,
        "expires_at": job.expires_at,
        "created_at": job.created_at,
    }


class ExportJobsView(APIView):
    model = None
    capability = None
    filters_class = None

    def get(self, request, organization_id):
        get_organization(
            actor=request.user, organization_id=organization_id, capability=self.capability
        )
        from apps.core.pagination import DefaultCursorPagination

        paginator = DefaultCursorPagination()
        rows = paginator.paginate_queryset(
            self.model.objects.filter(organization_id=organization_id), request
        )
        return paginator.get_paginated_response([job_output(row) for row in rows])

    @transaction.atomic
    def post(self, request, organization_id):
        get_organization(
            actor=request.user,
            organization_id=organization_id,
            capability=self.capability,
            lock=True,
        )
        filters = {
            key: value.isoformat() if hasattr(value, "isoformat") else str(value)
            for key, value in validated(self.filters_class, request).items()
        }
        with creation_command(
            actor_id=request.user.id,
            scope=f"export:{self.capability}:{organization_id}",
            key=request.headers.get("Idempotency-Key", ""),
            values=filters,
        ) as command:
            if command.resource_id:
                return Response(
                    {"data": job_output(self.model.objects.get(pk=command.resource_id))}, status=200
                )
            if (
                self.model.objects.filter(
                    organization_id=organization_id,
                    created_at__gt=timezone.now() - timedelta(hours=1),
                ).count()
                >= 10
            ):
                raise ConflictError(message="The hourly export limit has been reached.")
            job = self.model.objects.create(
                organization_id=organization_id,
                actor_id=request.user.id,
                filters=filters,
                expires_at=timezone.now() + timedelta(hours=24),
            )
            record_event(
                action=f"{self.capability}.export_requested",
                actor_id=request.user.id,
                organization_id=organization_id,
                target_id=job.id,
                target_type=self.model._meta.label,
            )
            remember_created(command, job.id)
            return Response({"data": job_output(job)}, status=202)


class UsageExportsView(ExportJobsView):
    model, capability, filters_class = UsageExport, "usage", UsageFilters


class AuditExportsView(ExportJobsView):
    model, capability, filters_class = AuditExport, "audit", AuditFilters


class ExportView(APIView):
    model = None
    capability = None
    download = False

    def get(self, request, organization_id, export_id):
        get_organization(
            actor=request.user, organization_id=organization_id, capability=self.capability
        )
        job = self.model.objects.filter(pk=export_id, organization_id=organization_id).first()
        if job is None:
            raise NotFoundError()
        if not self.download:
            return Response({"data": job_output(job)})
        if job.status != "ready" or job.expires_at <= timezone.now():
            raise ConflictError(message="This export is not available for download.")
        path = export_path(job)
        if not path.is_file() or path.is_symlink():
            raise NotFoundError(message="The export file is unavailable.")
        record_event(
            action=f"{self.capability}.export_downloaded",
            actor_id=request.user.id,
            organization_id=organization_id,
            target_id=job.id,
            target_type=self.model._meta.label,
        )
        return FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename=f"devvault-{self.capability}-{job.id}.csv",
            content_type="text/csv",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )


class UsageExportView(ExportView):
    model, capability = UsageExport, "usage"


class AuditExportView(ExportView):
    model, capability = AuditExport, "audit"
