import os

from django.core.exceptions import ImproperlyConfigured

from config.settings.base import *

required_environment = (
    "DJANGO_SECRET_KEY",
    "ACCOUNT_JWT_SIGNING_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DATABASE_URL",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "ACCOUNT_PUBLIC_BASE_URL",
    "DEFAULT_FROM_EMAIL",
    "EMAIL_HOST",
)
missing_environment = [name for name in required_environment if not os.environ.get(name)]
if missing_environment:
    raise ImproperlyConfigured(
        "Missing required production environment variables: " + ", ".join(missing_environment)
    )

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_HSTS_PRELOAD", default=False)
X_FRAME_OPTIONS = "DENY"
