"""The complete verification path with real Redis; PostgreSQL in the integration run."""

import os
from io import StringIO

import pytest
from django.core.management import call_command

from apps.access.rate_limits import _client
from apps.access.services import create_policy
from apps.access.tests.test_access import access, verify  # noqa: F401
from apps.projects.tests.test_projects import client_for, resources  # noqa: F401
from apps.usage.models import UsageEvent
from apps.usage.services import aggregate_pending

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        not os.environ.get("DEVVAULT_TEST_REDIS_URL"), reason="Opt-in full Redis verification"
    ),
]


def test_verify_replay_rate_denial_reporting_and_revoke(access, settings):
    settings.REDIS_URL = os.environ["DEVVAULT_TEST_REDIS_URL"]
    owner, org, service, _, issued, _ = access
    rate, _ = create_policy(
        actor=owner,
        organization_id=org.id,
        service_id=service.id,
        name="End-to-end rate",
        environment_kind="test",
        algorithm="fixed_window",
        dimension="key",
        config={"limit": 1, "window_seconds": 3600},
        idempotency_key="real-rate",
    )
    create_policy(
        actor=owner,
        organization_id=org.id,
        service_id=service.id,
        name="End-to-end quota",
        environment_kind="test",
        algorithm="daily",
        dimension="key",
        config={"limit": 10},
        idempotency_key="real-quota",
    )
    counter = f"dv:rate:{{{org.id}}}:test:{rate.id}:v1:{issued.resource.family_id}"
    try:
        assert verify(access, command="first", units=2).status_code == 200
        assert verify(access, command="first", units=2).data["data"]["replayed"]
        assert verify(access, command="second").status_code == 429
        assert UsageEvent.objects.count() == 2
        aggregate_pending()
        call_command("reconcile_usage", stdout=StringIO())
        client = client_for(owner)
        report = client.get(f"/api/v1/organizations/{org.id}/usage/")
        assert report.data["data"]["summary"]["units"] == 2
        response = client.post(
            f"/api/v1/keys/{issued.resource.id}/revoke/", {"confirm": True}, format="json"
        )
        assert response.status_code == 200
        assert verify(access, command="first", units=2).status_code == 401
    finally:
        _client(settings.REDIS_URL).delete(counter)
