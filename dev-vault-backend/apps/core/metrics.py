import os

from django.conf import settings
from django.http import HttpResponse
from django.utils.crypto import constant_time_compare
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

REQUESTS = Counter(
    "devvault_http_requests_total", "Completed HTTP requests", ("method", "route", "status")
)
LATENCY = Histogram(
    "devvault_http_request_duration_seconds",
    "HTTP request latency",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def record_request(method, route, status, elapsed):
    if route and route.endswith("metrics/"):
        return
    method = (
        method
        if method in {"GET", "POST", "PATCH", "PUT", "DELETE", "HEAD", "OPTIONS"}
        else "OTHER"
    )
    route = route or "unresolved"
    REQUESTS.labels(method, route, str(status)).inc()
    LATENCY.labels(method, route).observe(elapsed)


def metrics(request):
    token = settings.METRICS_TOKEN
    if len(token) < 32 or not constant_time_compare(
        request.headers.get("Authorization", ""), "Bearer " + token
    ):
        return HttpResponse(status=404)
    registry = REGISTRY
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    return HttpResponse(
        generate_latest(registry),
        content_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-store"},
    )
