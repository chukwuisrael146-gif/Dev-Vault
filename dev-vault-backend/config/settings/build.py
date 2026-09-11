"""Static-asset compilation only. Never a server's runtime settings module."""

from config.settings.base import *

SECRET_KEY = "build-only-no-runtime-signing"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
