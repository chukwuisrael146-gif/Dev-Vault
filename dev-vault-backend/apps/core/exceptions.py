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
