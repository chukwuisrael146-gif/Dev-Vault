from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection

from apps.access.tests.test_access import access, quota  # noqa: F401
from apps.access.verification import verify_access
from apps.credentials.services import issue_key
from apps.projects.tests.test_projects import resources  # noqa: F401
from apps.usage.models import QuotaReservation, UsageEvent

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="PostgreSQL row-lock concurrency test"
    ),
]


def execute_parallel(access, keys, command_ids):
    _, _, service, _, _, integration = access
    barrier = Barrier(len(keys))

    def run(pair):
        raw, command = pair
        close_old_connections()
        try:
            barrier.wait(timeout=20)
            return verify_access(
                integration_secret=integration.raw_value,
                raw_key=raw,
                service_id=service.id,
                environment="test",
                audience=service.audience,
                required_scopes=["orders:read"],
                idempotency_key=command,
            )[1]
        finally:
            close_old_connections()

    with (
        patch(
            "apps.access.verification.consume_rates",
            return_value={"allowed": True, "limits": [], "retry_after": 0},
        ),
        ThreadPoolExecutor(max_workers=len(keys)) as pool,
    ):
        return list(pool.map(run, zip(keys, command_ids, strict=True)))


def test_concurrent_retries_make_one_reservation(access):
    quota(access)
    results = execute_parallel(access, [access[4].raw_value] * 8, ["retry"] * 8)
    assert results == [200] * 8
    assert UsageEvent.objects.count() == QuotaReservation.objects.count() == 1


def test_shared_quota_cannot_be_overspent_by_different_keys(access):
    owner, _, service, permission, _, _ = access
    quota(access, limit=3, dimension="shared")
    keys = [
        issue_key(
            actor=owner,
            service_id=service.id,
            name="Concurrent",
            permission_ids=[permission.id],
            idempotency_key=str(uuid4()),
        ).raw_value
        for _ in range(8)
    ]
    results = execute_parallel(access, keys, [str(uuid4()) for _ in keys])
    assert results.count(200) == 3 and results.count(429) == 5
    assert QuotaReservation.objects.count() == 3
