from django.urls import path

from apps.core.health import liveness, readiness

app_name = "core"

urlpatterns = [
    path("live/", liveness, name="liveness"),
    path("ready/", readiness, name="readiness"),
]
