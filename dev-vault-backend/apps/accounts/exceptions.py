from http import HTTPStatus

from apps.core.exceptions import DomainError


class EmailAlreadyRegisteredError(DomainError):
    code = "email_already_registered"
    message = "An account with this email address already exists."
    status_code = HTTPStatus.CONFLICT


class InvalidEmailVerificationError(DomainError):
    code = "invalid_verification_token"
    message = "This verification link is invalid or expired. Request a new link."


class AccountSecurityUnavailableError(DomainError):
    code = "account_security_unavailable"
    message = "Account requests are temporarily unavailable. Please try again later."
    status_code = HTTPStatus.SERVICE_UNAVAILABLE


class InvalidLoginError(DomainError):
    code = "invalid_credentials"
    message = "Email or password is incorrect."
    status_code = HTTPStatus.UNAUTHORIZED


class InvalidSessionTokenError(DomainError):
    code = "invalid_token"
    message = "The token is invalid or expired. Please sign in again."
    status_code = HTTPStatus.UNAUTHORIZED
