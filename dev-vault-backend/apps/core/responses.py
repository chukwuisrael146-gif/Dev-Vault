import logging
from http import HTTPStatus
from typing import Any

from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.exceptions import DomainError

logger = logging.getLogger(__name__)


def _request_id(request: Any) -> str | None:
    return getattr(request, "correlation_id", None) if request is not None else None


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: Any = None,
    request: Any = None,
) -> Response:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "details": details if details is not None else {},
        "request_id": _request_id(request),
    }
    return Response({"error": error}, status=status_code)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    request = context.get("request")

    if isinstance(exc, DomainError):
        return error_response(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            status_code=int(exc.status_code),
            request=request,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        code = "validation_error" if isinstance(exc, ValidationError) else "request_error"
        if (
            not isinstance(exc, ValidationError)
            and isinstance(exc, APIException)
            and isinstance(exc.default_code, str)
        ):
            code = exc.default_code
        message = (
            "The request contains invalid data." if isinstance(exc, ValidationError) else str(exc)
        )
        details = response.data
        response.data = {
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": _request_id(request),
            }
        }
        return response

    logger.exception("Unhandled API exception", extra={"outcome": "internal_error"})
    return error_response(
        code="internal_error",
        message="An unexpected error occurred.",
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        request=request,
    )
