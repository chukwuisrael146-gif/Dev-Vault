"""Release configuration checks. Messages intentionally exclude configured values."""

import hashlib
from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Error, register


def https_origin(value):
    try:
        url = urlsplit(value)
        return bool(
            url.scheme == "https" and url.hostname and not url.username and not url.password
            and url.path in {"", "/"} and not url.query and not url.fragment
            and url.port in {None, 443}
        )
    except (TypeError, ValueError):
        return False


@register(deploy=True)
def production_checks(app_configs, **kwargs):
    if not getattr(settings, "PRODUCTION", False):
        return []
    errors = []

    def require(condition, code, message):
        if not condition:
            errors.append(Error(message, id=f"core.{code}"))

    require(not settings.DEBUG and settings.SECURE_SSL_REDIRECT, "E101",
            "Production requires DEBUG=False and HTTPS redirection.")
    require(settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE, "E102",
            "Production cookies must be secure.")
    require(settings.SECURE_HSTS_SECONDS > 0, "E103", "Production requires a positive HSTS lifetime.")
    require(bool(settings.ALLOWED_HOSTS) and all(
        host and "*" not in host and not host.startswith(".") and "://" not in host
        for host in settings.ALLOWED_HOSTS
    ), "E104", "Configure explicit production hostnames, never wildcard hosts.")
    require(https_origin(settings.ACCOUNT_PUBLIC_BASE_URL), "E105",
            "Account links require a public HTTPS origin in production.")
    require(all(https_origin(origin) for origin in [
        *settings.CORS_ALLOWED_ORIGINS, *settings.CSRF_TRUSTED_ORIGINS
    ]), "E106", "Production browser origins must be explicit HTTPS origins.")
    require(settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql", "E107",
            "Production requires PostgreSQL.")
    for setting in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        try:
            url = urlsplit(getattr(settings, setting))
            valid = url.scheme in {"redis", "rediss"} and bool(url.hostname)
        except ValueError:
            valid = False
        require(valid, "E108", f"{setting} must identify a private Redis-compatible service.")
    require(len(settings.SECRET_KEY) >= 50 and len(set(settings.SECRET_KEY)) >= 5
            and not any(word in settings.SECRET_KEY.lower() for word in ("unsafe", "replace-with", "change-me")),
            "E109", "Use a long independently generated production Django secret.")
    derived_jwt = hashlib.sha256(f"devvault.jwt.development:{settings.SECRET_KEY}".encode()).hexdigest()
    require(settings.ACCOUNT_JWT_SIGNING_KEY != derived_jwt, "E110",
            "Development-derived JWT keys are not allowed in production.")
    require(len(settings.METRICS_TOKEN) >= 32 and settings.METRICS_TOKEN not in {
        settings.SECRET_KEY, settings.ACCOUNT_JWT_SIGNING_KEY
    }, "E111", "Use an independent 32+ character metrics token.")
    mailer = settings.MAILERS["default"]
    options = mailer.get("OPTIONS", {})
    require(mailer["BACKEND"] == "django.core.mail.backends.smtp.EmailBackend"
            and bool(options.get("use_tls")) != bool(options.get("use_ssl")), "E112",
            "Production SMTP requires exactly one of TLS or SSL.")
    require(settings.EXPORT_STORAGE_BACKEND in {"local", "s3"}, "E113",
            "Choose the local or s3 export storage backend.")
    if settings.EXPORT_STORAGE_BACKEND == "s3":
        require(bool(settings.EXPORT_S3_BUCKET and settings.EXPORT_S3_REGION), "E114",
                "S3 export storage requires a private bucket and explicit region.")
    require(1024 <= settings.EXPORT_MAX_BYTES <= 50 * 1024 * 1024, "E115",
            "Export byte limits must be between 1 KiB and 50 MiB.")
    if getattr(settings, "RENDER_DEPLOYMENT", False):
        require(settings.EXPORT_STORAGE_BACKEND == "s3", "E116",
                "Render web and worker services require shared S3 export storage.")
    return errors
