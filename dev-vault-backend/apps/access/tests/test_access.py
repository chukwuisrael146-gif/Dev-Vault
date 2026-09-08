from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import OperationalError
from rest_framework.test import APIClient

from apps.access.models import PolicyRevision, QuotaBucket
from apps.access.quotas import period_bounds
from apps.access.services import create_permission, create_policy
from apps.core.exceptions import DependencyUnavailableError
from apps.credentials.services import issue_integration_credential, issue_key
from apps.projects.tests.test_projects import client_for, resources  # noqa: F401
from apps.usage.models import QuotaReservation, UsageAggregate, UsageEvent
from apps.usage.services import aggregate_pending

pytestmark = pytest.mark.django_db


@pytest.fixture
def access(resources):
    owner, organization, project, environment, service = resources
    permission, _ = create_permission(
        actor=owner, service_id=service.id, name="orders:read", idempotency_key="scope"
    )
    key = issue_key(
        actor=owner,
        service_id=service.id,
        name="Consumer",
        permission_ids=[permission.id],
        idempotency_key="consumer",
    )
    integration = issue_integration_credential(
        actor=owner, service_id=service.id, name="Backend", idempotency_key="backend"
    )
    return owner, organization, service, permission, key, integration


@pytest.fixture(autouse=True)
def rates():
    with patch(
        "apps.access.verification.consume_rates",
        return_value={"allowed": True, "limits": [], "retry_after": 0},
    ) as mocked:
        yield mocked


def verify(access, command=None, **values):
    _, _, service, _, key, integration = access
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION="Bearer " + values.pop("raw_key", key.raw_value),
        HTTP_X_DEVVAULT_SERVICE_TOKEN=values.pop("integration_secret", integration.raw_value),
    )
    return client.post(
        "/api/v1/access/verify/",
        {
            "service_id": str(service.id),
            "environment": "test",
            "audience": service.audience,
            "required_scopes": ["orders:read"],
            **values,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=command or str(uuid4()),
    )


def quota(access, limit=5, dimension="key"):
    owner, org, service, _, _, _ = access
    return create_policy(
        actor=owner,
        organization_id=org.id,
        service_id=service.id,
        name="Daily budget",
        environment_kind="test",
        algorithm="daily",
        dimension=dimension,
        config={"limit": limit},
        idempotency_key=f"quota-{dimension}",
    )[0]


def test_valid_context_exact_scopes_and_credential_separation(access):
    result = verify(access)
    assert result.status_code == 200 and result.data["data"]["allowed"]
    assert result["Cache-Control"] == "no-store"
    assert verify(access, required_scopes=["orders:write"]).status_code == 403
    assert (
        verify(
            access, required_scopes=["orders:read", "orders:write"], scope_mode="any"
        ).status_code
        == 200
    )
    assert verify(access, required_scopes=["orders:*"]).status_code == 400
    assert verify(access, audience="other-api").status_code == 401
    assert verify(access, environment="live").status_code == 401
    assert verify(access, service_id=str(uuid4())).status_code == 401
    assert verify(access, integration_secret=access[4].raw_value).status_code == 401
    assert verify(access, raw_key=access[5].raw_value).status_code == 401
    assert APIClient().post("/api/v1/access/verify/", {}, format="json").status_code == 401
    assert verify(access, units=0).status_code == 400
    assert verify(access, unexpected="ignored?").status_code == 400


def test_weighted_quota_idempotency_and_durable_facts(access):
    quota(access)
    result = verify(access, command="same", units=3)
    assert result.status_code == 200
    assert result.data["data"]["quotas"][0]["remaining"] == 2
    assert verify(access, command="same", units=3).data["data"]["replayed"]
    assert verify(access, command="same", units=1).status_code == 409
    assert QuotaBucket.objects.get().used == 3
    assert UsageEvent.objects.count() == QuotaReservation.objects.count() == 1
    denied = verify(access, units=3)
    assert denied.status_code == 429 and denied.data["error"]["code"] == "quota_exceeded"
    assert int(denied["Retry-After"]) > 0
    assert QuotaBucket.objects.get().used == 3
    assert verify(access, units=2).status_code == 200
    assert QuotaBucket.objects.get().used == 5
    assert aggregate_pending() == 3
    assert aggregate_pending() == 0
    assert sum(row.requests for row in UsageAggregate.objects.all()) == 3
    assert sum(row.units for row in UsageAggregate.objects.all()) == 5
    assert access[4].raw_value not in repr(list(UsageEvent.objects.values()))
    with pytest.raises(TypeError):
        UsageEvent.objects.all().update(units=999)


def test_rate_denial_does_not_consume_quota_and_outage_rolls_back(access, rates):
    quota(access)
    rates.return_value = {"allowed": False, "limits": [], "retry_after": 3}
    result = verify(access)
    assert result.status_code == 429 and result["Retry-After"] == "3"
    assert QuotaBucket.objects.get().used == 0
    assert QuotaReservation.objects.count() == 0
    rates.side_effect = DependencyUnavailableError(code="enforcement_unavailable")
    assert verify(access).status_code == 503
    assert UsageEvent.objects.count() == 1
    assert QuotaBucket.objects.get().used == 0


def test_usage_write_failure_cannot_commit_allowance(access):
    quota(access)
    with patch(
        "apps.access.verification.UsageEvent.objects.create",
        side_effect=RuntimeError("outbox unavailable"),
    ):
        assert verify(access).status_code == 500
    assert (
        QuotaBucket.objects.count()
        == QuotaReservation.objects.count()
        == UsageEvent.objects.count()
        == 0
    )


def test_database_outage_returns_retryable_failure(access):
    with patch("api.v1.access.verification.verify_access", side_effect=OperationalError("offline")):
        response = verify(access)
    assert response.status_code == 503
    assert response.data["error"]["code"] == "enforcement_unavailable"
    assert UsageEvent.objects.count() == 0


def test_policy_revision_preserves_quota_and_stale_edits_fail(access):
    owner = access[0]
    policy = quota(access)
    assert verify(access, units=4).status_code == 200
    client = client_for(owner)
    path = f"/api/v1/policies/{policy.id}/"
    response = client.patch(
        path, {"expected_version": 1, "confirm": True, "config": {"limit": 3}}, format="json"
    )
    assert response.status_code == 200 and response.data["data"]["version"] == 2
    assert PolicyRevision.objects.filter(policy=policy).count() == 2
    assert verify(access).status_code == 429
    assert QuotaBucket.objects.get().used == 4
    assert (
        client.patch(
            path, {"expected_version": 1, "confirm": True, "config": {"limit": 50}}, format="json"
        ).status_code
        == 409
    )
    assert (
        client.patch(
            path, {"expected_version": 2, "confirm": True, "algorithm": "monthly"}, format="json"
        ).status_code
        == 400
    )


def test_rotation_copies_grants_but_does_not_reset_quota(access):
    owner, _, _, permission, key, _ = access
    quota(access)
    assert verify(access, command="before", units=5).status_code == 200
    client = client_for(owner)
    response = client.post(
        f"/api/v1/keys/{key.resource.id}/rotate/",
        {"confirm": True, "overlap_seconds": 30},
        format="json",
        HTTP_IDEMPOTENCY_KEY="rotate",
    )
    assert response.status_code == 201
    assert verify(access, raw_key=response.data["data"]["secret"]).status_code == 429
    assert QuotaBucket.objects.count() == 1
    assert (
        client.post(
            f"/api/v1/keys/{key.resource.id}/revoke/", {"confirm": True}, format="json"
        ).status_code
        == 200
    )
    assert verify(access, command="before", units=5).status_code == 401


def test_scope_removal_confirmation_and_replay_guard(access):
    owner, _, service, permission, key, _ = access
    assert verify(access, command="original").status_code == 200
    client = client_for(owner)
    path = f"/api/v1/keys/{key.resource.id}/permissions/"
    assert client.put(path, {"permission_ids": []}, format="json").status_code == 400
    assert (
        client.put(path, {"permission_ids": [], "confirm": True}, format="json").status_code == 200
    )
    assert verify(access, command="original").status_code == 403
    assert (
        client.put(path, {"permission_ids": [str(permission.id)]}, format="json").status_code == 200
    )
    assert (
        client.get(f"/api/v1/services/{service.id}/permissions/{permission.id}/impact/").data[
            "data"
        ]["affected_keys"]
        == 1
    )
    assert (
        client.post(
            f"/api/v1/services/{service.id}/permissions/{permission.id}/status/",
            {"is_active": False, "confirm": True},
            format="json",
        ).status_code
        == 200
    )
    assert verify(access).status_code == 403


def test_adjustment_ledger_is_idempotent_and_does_not_rewrite_usage(access):
    policy = quota(access, limit=1, dimension="shared")
    assert verify(access).status_code == 200
    assert verify(access).status_code == 429
    client = client_for(access[0])
    path = f"/api/v1/policies/{policy.id}/quota-adjustments/"
    body = {"delta": 2, "reason": "Approved support credit", "confirm": True}
    assert client.post(path, body, format="json", HTTP_IDEMPOTENCY_KEY="credit").status_code == 201
    assert client.post(path, body, format="json", HTTP_IDEMPOTENCY_KEY="credit").status_code == 200
    bucket = QuotaBucket.objects.get()
    assert bucket.used == 1 and bucket.adjustment == 2
    assert verify(access, units=2).status_code == 200


@pytest.mark.parametrize(
    "algorithm,instant,end",
    [
        ("daily", datetime(2026, 12, 31, 23, 59, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)),
        ("monthly", datetime(2026, 12, 15, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)),
        ("monthly", datetime(2028, 2, 29, tzinfo=UTC), datetime(2028, 3, 1, tzinfo=UTC)),
    ],
)
def test_quota_calendar_boundaries(algorithm, instant, end):
    start, actual_end = period_bounds(algorithm, instant)
    assert start <= instant < actual_end and actual_end == end
