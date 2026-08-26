from config.settings.base import *

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
MAILERS["default"] = {"BACKEND": "django.core.mail.backends.console.EmailBackend"}

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] += [
    "rest_framework.renderers.BrowsableAPIRenderer",
]
