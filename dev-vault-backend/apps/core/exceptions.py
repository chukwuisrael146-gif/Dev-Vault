from collections.abc import Mapping
from http import HTTPStatus
from typing import Any


class DomainError(Exception):
    """Known, safely presentable domain failure independent of HTTP/DRF."""

    code = "domain_error"
    message = "The requested operation could not be completed."
    status_code = HTTPStatus.BAD_REQUEST

    def __init__(
        self,
        *,
        code: str | None = None,
        message: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code or self.code
        self.message = message or self.message
        self.details = dict(details or {})
        super().__init__(self.message)


class NotFoundError(DomainError):
    code = "not_found"
    message = "The requested resource was not found."
    status_code = HTTPStatus.NOT_FOUND


class ForbiddenError(DomainError):
    code = "permission_denied"
    message = "You do not have permission to perform this action."
    status_code = HTTPStatus.FORBIDDEN


class ConflictError(DomainError):
    code = "conflict"
    message = "The requested operation conflicts with the current resource state."
    status_code = HTTPStatus.CONFLICT


class DependencyUnavailableError(DomainError):
    code = "service_unavailable"
    message = "A required service is temporarily unavailable."
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
