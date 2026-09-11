import os

from django.core.exceptions import ImproperlyConfigured

from config.settings.base import *

required_environment = (
    "DJANGO_SECRET_KEY",
    "ACCOUNT_JWT_SIGNING_KEY",
    "API_KEY_PEPPERS",
    "WEBHOOK_ENCRYPTION_KEYS",
    "DJANGO_ALLOWED_HOSTS",
    "DATABASE_URL",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "ACCOUNT_PUBLIC_BASE_URL",
    "DEFAULT_FROM_EMAIL",
    "EMAIL_HOST",
    "METRICS_TOKEN",
)
missing_environment = [name for name in required_environment if not os.environ.get(name)]
if missing_environment:
    raise ImproperlyConfigured(
        "Missing required production environment variables: " + ", ".join(missing_environment)
    )

DEBUG = False
PRODUCTION = True
if not env.json("API_KEY_PEPPERS", default={}):
    raise ImproperlyConfigured("Production requires independently generated API key peppers.")
if not env.json("WEBHOOK_ENCRYPTION_KEYS", default=[]):
    raise ImproperlyConfigured("Production requires independent webhook encryption keys.")
# Trust this only behind an ingress that strips caller-supplied forwarding headers.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env.bool("DJANGO_TRUST_PROXY", default=False)
    else None
)
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_HSTS_PRELOAD", default=False)
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "no-referrer"
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_USE_FINDERS = False
WHITENOISE_AUTOREFRESH = False

DATABASES["default"].setdefault("OPTIONS", {}).update(
    connect_timeout=5,
    options="-c statement_timeout=30000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=60000",
)
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
CELERY_BROKER_CONNECTION_TIMEOUT = 5
CELERY_RESULT_EXPIRES = 3600
CELERY_BROKER_TRANSPORT_OPTIONS = {"socket_connect_timeout": 5, "socket_timeout": 5}
# Periodic jobs poll durable records. Do not endlessly redeliver poisoned jobs.
for scheduled_job in CELERY_BEAT_SCHEDULE.values():
    scheduled_job.setdefault("options", {}).setdefault("expires", scheduled_job["schedule"])
