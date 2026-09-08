from django.contrib import admin
from django.urls import include, path

from apps.core.metrics import metrics

urlpatterns = [
    path("internal/metrics/", metrics, name="metrics"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
