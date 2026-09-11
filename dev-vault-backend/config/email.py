"""Explicit local mail transport selection; no credentials in validation messages."""

from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured


def development_mailer(*, mode, smtp_mailer, base_dir):
    if mode == "file":
        return {
            "BACKEND": "django.core.mail.backends.filebased.EmailBackend",
            "OPTIONS": {"file_path": base_dir / "var" / "emails"},
        }
    if mode != "smtp":
        raise ImproperlyConfigured("DJANGO_EMAIL_MODE must be file or smtp.")
    options = smtp_mailer["OPTIONS"]
    if options.get("use_tls") and options.get("use_ssl"):
        raise ImproperlyConfigured("Enable EMAIL_USE_TLS or EMAIL_USE_SSL, not both.")
    if options.get("host") not in {"localhost", "127.0.0.1", "::1"} and not (
        options.get("use_tls") or options.get("use_ssl")
    ):
        raise ImproperlyConfigured("Remote SMTP requires TLS or SSL.")
    if bool(options.get("username")) != bool(options.get("password")):
        raise ImproperlyConfigured("Configure both EMAIL_HOST_USER and EMAIL_HOST_PASSWORD.")
    return deepcopy(smtp_mailer)
