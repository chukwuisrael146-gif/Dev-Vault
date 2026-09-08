from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api.v1 import reporting, webhooks
from api.v1.accounts.profile import CurrentUserView, PasswordChangeView

urlpatterns = [
    path(
        "schema/",
        SpectacularAPIView.as_view(authentication_classes=[], permission_classes=[]),
        name="api-schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="api-schema", authentication_classes=[], permission_classes=[]
        ),
        name="api-docs",
    ),
    path("organizations/<uuid:organization_id>/webhooks/", webhooks.EndpointsView.as_view()),
    path(
        "organizations/<uuid:organization_id>/webhooks/<uuid:endpoint_id>/status/",
        webhooks.EndpointStatusView.as_view(),
    ),
    path(
        "organizations/<uuid:organization_id>/webhooks/<uuid:endpoint_id>/rotate-secret/",
        webhooks.EndpointSecretView.as_view(),
    ),
    path(
        "organizations/<uuid:organization_id>/webhooks/<uuid:endpoint_id>/deliveries/",
        webhooks.DeliveriesView.as_view(),
    ),
    path(
        "organizations/<uuid:organization_id>/webhooks/<uuid:endpoint_id>/deliveries/<uuid:delivery_id>/attempts/",
        webhooks.DeliveryAttemptsView.as_view(),
    ),
    path(
        "organizations/<uuid:organization_id>/webhooks/<uuid:endpoint_id>/deliveries/<uuid:delivery_id>/retry/",
        webhooks.DeliveryRetryView.as_view(),
    ),
    path("organizations/<uuid:organization_id>/usage/", reporting.UsageView.as_view()),
    path("organizations/<uuid:organization_id>/usage/events/", reporting.UsageEventsView.as_view()),
    path("organizations/<uuid:organization_id>/audit-logs/", reporting.AuditLogsView.as_view()),
    path(
        "organizations/<uuid:organization_id>/usage/exports/", reporting.UsageExportsView.as_view()
    ),
    path(
        "organizations/<uuid:organization_id>/usage/exports/<uuid:export_id>/",
        reporting.UsageExportView.as_view(),
    ),
    path(
        "organizations/<uuid:organization_id>/usage/exports/<uuid:export_id>/download/",
        reporting.UsageExportView.as_view(download=True),
    ),
    path(
        "organizations/<uuid:organization_id>/audit-logs/exports/",
        reporting.AuditExportsView.as_view(),
    ),
    path(
        "organizations/<uuid:organization_id>/audit-logs/exports/<uuid:export_id>/",
        reporting.AuditExportView.as_view(),
    ),
    path(
        "organizations/<uuid:organization_id>/audit-logs/exports/<uuid:export_id>/download/",
        reporting.AuditExportView.as_view(download=True),
    ),
    path("", include("api.v1.access.urls")),
    path("", include("api.v1.credentials.urls")),
    path("", include("api.v1.projects.urls")),
    path("", include("api.v1.organizations.urls")),
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("me/password/", PasswordChangeView.as_view(), name="password-change"),
    path("auth/", include("api.v1.accounts.urls")),
    path("health/", include("apps.core.urls")),
]
