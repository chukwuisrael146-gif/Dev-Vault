from http import HTTPStatus

from apps.core.exceptions import DomainError


class EmailAlreadyRegisteredError(DomainError):
    code = "email_already_registered"
    message = "An account with this email address already exists."
    status_code = HTTPStatus.CONFLICT