from config.settings.base import *

DEBUG = False
SECRET_KEY = "test-only-key"
ALLOWED_HOSTS = ["testserver"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "devvault-tests",
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
MAILERS["default"] = {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
LOGGING["root"]["level"] = "CRITICAL"
