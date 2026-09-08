import os
from pathlib import Path

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("WEB_THREADS", "4"))
timeout = 30
graceful_timeout = 30
keepalive = 5
# Django logs route templates; raw URI access logs may expose query secrets.
accesslog = None
errorlog = "-"
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "safe": {
            "()": "apps.core.logging.SafeJsonFormatter",
            "service": "devvault-web",
            "environment": os.environ.get("DJANGO_ENVIRONMENT", "production"),
            "deployment_version": os.environ.get("DEPLOYMENT_VERSION", "unknown"),
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "safe"},
        "discard": {"class": "logging.NullHandler"},
    },
    # Gunicorn shallow-merges its default loggers. Override both so no logger
    # refers to a removed default handler or writes a raw-URI access record.
    "loggers": {
        "gunicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "gunicorn.access": {"handlers": ["discard"], "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


def on_starting(server):
    # Container /tmp is a fresh tmpfs per start. Never remove a broad/shared directory.
    directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)


def child_exit(server, worker):
    from prometheus_client import multiprocess

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.mark_process_dead(worker.pid)
