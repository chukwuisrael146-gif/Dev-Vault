import logging
import re
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.context import correlation_id_context

logger = logging.getLogger("devvault.request")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CorrelationIdMiddleware:
    header_name = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        candidate = request.META.get(self.header_name, "")
        correlation_id = candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid.uuid4())
        request.correlation_id = correlation_id
        token = correlation_id_context.set(correlation_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = correlation_id
            return response
        finally:
            correlation_id_context.reset(token)


class RequestLoggingMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started_at = time.perf_counter()
        response = self.get_response(request)
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        route = getattr(getattr(request, "resolver_match", None), "route", None)
        status_code = response.status_code
        if status_code < 400:
            outcome = "success"
        elif status_code < 500:
            outcome = "client_error"
        else:
            outcome = "server_error"
        logger.info(
            "HTTP request completed",
            extra={
                "method": request.method,
                "route": route or "unresolved",
                "status_code": status_code,
                "outcome": outcome,
                "latency_ms": latency_ms,
            },
        )
        return response
