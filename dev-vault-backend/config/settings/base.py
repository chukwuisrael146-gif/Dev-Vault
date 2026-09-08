import base64
import hashlib
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_READ_ENV_FILE=(bool, False),
    READINESS_CHECK_MIGRATIONS=(bool, True),
)

if env.bool("DJANGO_READ_ENV_FILE", default=False):
    env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-development-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.projects",
    "apps.credentials",
    "apps.access",
    "apps.usage",
    "apps.audit",
    "apps.webhooks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware.CorrelationIdMiddleware",
    "apps.core.middleware.RequestLoggingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgresql://devvault:devvault@127.0.0.1:5432/devvault",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        "KEY_PREFIX": "devvault:v1",
        "TIMEOUT": 300,
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SOFT_TIME_LIMIT = 300
CELERY_TASK_TIME_LIMIT = 330
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "deliver-webhook-events": {"task": "apps.webhooks.tasks.deliver_webhooks", "schedule": 10.0},
    "process-usage-exports": {"task": "apps.usage.exports.process_usage_exports", "schedule": 30.0},
    "process-audit-exports": {"task": "apps.audit.tasks.process_audit_exports", "schedule": 30.0},
    "aggregate-usage-events": {
        "task": "apps.usage.tasks.aggregate_usage",
        "schedule": 10.0,
        "options": {"expires": 10},
    },
    "deliver-organization-invitations": {
        "task": "apps.organizations.tasks.deliver_invitations",
        "schedule": 30.0,
        "options": {"expires": 30},
    },
    "deliver-account-password-resets": {
        "task": "apps.accounts.tasks.deliver_pending_resets",
        "schedule": 30.0,
        "options": {"expires": 30},
    },
    "deliver-account-verification-emails": {
        "task": "apps.accounts.tasks.deliver_pending_verifications",
        "schedule": 30.0,
        "options": {"expires": 30},
    },
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("EMAIL_HOST", default="localhost"),
            "port": env.int("EMAIL_PORT", default=587),
            "username": env("EMAIL_HOST_USER", default=""),
            "password": env("EMAIL_HOST_PASSWORD", default=""),
            "use_tls": env.bool("EMAIL_USE_TLS", default=True),
            "use_ssl": env.bool("EMAIL_USE_SSL", default=False),
            "timeout": 10,
        },
    }
}

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="DevVault <noreply@devvault.local>")
ACCOUNT_PUBLIC_BASE_URL = env("ACCOUNT_PUBLIC_BASE_URL", default="http://127.0.0.1:8000")
EMAIL_VERIFICATION_TTL_SECONDS = env.int("EMAIL_VERIFICATION_TTL_SECONDS", default=1800)
PASSWORD_RESET_TTL_SECONDS = env.int("PASSWORD_RESET_TTL_SECONDS", default=1800)
EMAIL_VERIFICATION_RESEND_SECONDS = env.int("EMAIL_VERIFICATION_RESEND_SECONDS", default=60)
ACCOUNT_THROTTLE_RATES = {
    "password_reset": (10, 3600),
    "password_reset_confirm": (30, 60),
    "password_change": (10, 300),
    "login": (20, 300),
    "refresh": (60, 60),
    "logout": (60, 60),
    "register": (10, 3600),
    "verify_email": (30, 60),
    "resend_verification": (10, 3600),
}

ACCOUNT_JWT_SIGNING_KEY = (
    env("ACCOUNT_JWT_SIGNING_KEY", default="")
    or hashlib.sha256(f"devvault.jwt.development:{SECRET_KEY}".encode()).hexdigest()
)
ACCOUNT_JWT_ISSUER = env("ACCOUNT_JWT_ISSUER", default="devvault")
ACCOUNT_JWT_AUDIENCE = env("ACCOUNT_JWT_AUDIENCE", default="devvault-dashboard")
ACCOUNT_ACCESS_TOKEN_SECONDS = env.int("ACCOUNT_ACCESS_TOKEN_SECONDS", default=300)
ACCOUNT_REFRESH_TOKEN_SECONDS = env.int("ACCOUNT_REFRESH_TOKEN_SECONDS", default=604800)

API_KEY_ACTIVE_PEPPER_VERSION = env("API_KEY_ACTIVE_PEPPER_VERSION", default="1")
EXPORT_ROOT = BASE_DIR / "var" / "exports"
EXPORT_MAX_ROWS = 100000
METRICS_TOKEN = env("METRICS_TOKEN", default="")
WEBHOOK_DELIVERY_ENABLED = env.bool("WEBHOOK_DELIVERY_ENABLED", default=False)
WEBHOOK_ENCRYPTION_KEYS = env.json("WEBHOOK_ENCRYPTION_KEYS", default=[]) or [
    base64.urlsafe_b64encode(
        hashlib.sha256(("devvault.webhook.development:" + SECRET_KEY).encode()).digest()
    ).decode()
]
API_KEY_PEPPERS = env.json("API_KEY_PEPPERS", default={}) or {
    "1": hashlib.sha256(f"devvault.api-key.development:{SECRET_KEY}".encode()).hexdigest(),
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "api.v1.schema.DevVaultSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["api.v1.accounts.authentication.DashboardJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "api.v1.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["apps.core.parsers.BoundedJSONParser"],
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = False
SPECTACULAR_SETTINGS = {
    "POSTPROCESSING_HOOKS": [],
    "TITLE": "DevVault API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "DESCRIPTION": (
        "Tenant-scoped dashboard APIs and fail-closed server verification. "
        "All times UTC. Secrets appear once only. "
        "See docs/frontend-integration.md for integration and retry rules."
    ),
    "COMPONENT_SPLIT_REQUEST": True,
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "ConsumerKey": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "Bearer dv_test_* or Bearer dv_live_*. Not a dashboard JWT.",
            },
            "ServiceIntegration": {
                "type": "apiKey",
                "in": "header",
                "name": "X-DevVault-Service-Token",
                "description": "Private dvs_* server credential. Never place in browser code.",
            },
        }
    },
}
CORS_URLS_REGEX = r"^/api/v1/"
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-request-id",
    "idempotency-key",
]
CORS_EXPOSE_HEADERS = [
    "X-Request-ID",
    "Retry-After",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
]

READINESS_CHECK_MIGRATIONS = env.bool("READINESS_CHECK_MIGRATIONS", default=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_secrets": {"()": "apps.core.logging.RedactingFilter"},
    },
    "formatters": {
        "json": {
            "()": "apps.core.logging.SafeJsonFormatter",
            "service": "devvault-api",
            "environment": env("DJANGO_ENVIRONMENT", default="development"),
            "deployment_version": env("DEPLOYMENT_VERSION", default="unknown"),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["redact_secrets"],
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
