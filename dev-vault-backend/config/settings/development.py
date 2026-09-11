from config.email import development_mailer
from config.settings.base import *

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
DJANGO_EMAIL_MODE = env("DJANGO_EMAIL_MODE", default="file").strip().lower()
MAILERS["default"] = development_mailer(
    mode=DJANGO_EMAIL_MODE, smtp_mailer=MAILERS["default"], base_dir=BASE_DIR
)

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] += [
    "rest_framework.renderers.BrowsableAPIRenderer",
]
