from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Error, register


@register()
def check_verification_settings(app_configs, **kwargs):
    errors = []
    url = urlsplit(settings.ACCOUNT_PUBLIC_BASE_URL)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or (url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        errors.append(
            Error(
                "ACCOUNT_PUBLIC_BASE_URL must be an HTTPS origin (HTTP allowed only on localhost).",
                id="accounts.E001",
            )
        )
    if settings.EMAIL_VERIFICATION_TTL_SECONDS <= 0:
        errors.append(Error("Verification lifetime must be positive.", id="accounts.E002"))
    if settings.EMAIL_VERIFICATION_RESEND_SECONDS <= 0:
        errors.append(Error("Verification resend cooldown must be positive.", id="accounts.E003"))
    for limit, seconds in settings.ACCOUNT_THROTTLE_RATES.values():
        if limit <= 0 or seconds <= 0:
            errors.append(Error("Account throttle limits must be positive.", id="accounts.E004"))
    return errors


@register()
def check_jwt_settings(app_configs, **kwargs):
    errors = []
    if len(settings.ACCOUNT_JWT_SIGNING_KEY.encode()) < 32:
        errors.append(
            Error("ACCOUNT_JWT_SIGNING_KEY must be at least 32 bytes.", id="accounts.E005")
        )
    if not settings.ACCOUNT_JWT_ISSUER or not settings.ACCOUNT_JWT_AUDIENCE:
        errors.append(Error("JWT issuer and audience must not be empty.", id="accounts.E006"))
    if not 0 < settings.ACCOUNT_ACCESS_TOKEN_SECONDS <= 900:
        errors.append(Error("Access token lifetime must be 1–900 seconds.", id="accounts.E007"))
    if (
        not settings.ACCOUNT_ACCESS_TOKEN_SECONDS
        < settings.ACCOUNT_REFRESH_TOKEN_SECONDS
        <= 2592000
    ):
        errors.append(
            Error(
                "Refresh lifetime must exceed the access lifetime and be at most 30 days.",
                id="accounts.E008",
            )
        )
    if settings.ACCOUNT_JWT_SIGNING_KEY == settings.SECRET_KEY:
        errors.append(Error("Use an independent JWT signing key.", id="accounts.E009"))
    return errors
