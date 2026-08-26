import logging
import uuid
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _check_database() -> None:
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _check_cache() -> None:
    key = f"readiness:{uuid.uuid4()}"
    cache.set(key, "ready", timeout=5)
    if cache.get(key) != "ready":
        raise RuntimeError("Cache readiness probe did not round-trip")
    cache.delete(key)


def _check_migrations() -> None:
    connection = connections["default"]
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    if executor.migration_plan(targets):
        raise RuntimeError("Unapplied database migrations")


def get_readiness_status() -> tuple[bool, list[str]]:
    checks: dict[str, Callable[[], None]] = {
        "database": _check_database,
        "redis": _check_cache,
    }
    if settings.READINESS_CHECK_MIGRATIONS:
        checks["migrations"] = _check_migrations

    failed: list[str] = []
    for name, check in checks.items():
        try:
            check()
        except Exception as exc:  # dependency probes must collapse to a safe readiness result
            failed.append(name)
            logger.warning(
                "Readiness dependency failed",
                extra={
                    "outcome": "not_ready",
                    "dependency": name,
                    "error_type": type(exc).__name__,
                },
            )
    return not failed, failed


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def liveness(request) -> Response:
    return Response({"status": "ok"})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def readiness(request) -> Response:
    ready, _failed = get_readiness_status()
    return Response({"status": "ready" if ready else "not_ready"}, status=200 if ready else 503)
