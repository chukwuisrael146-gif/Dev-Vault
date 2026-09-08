from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditExport
from apps.audit.tasks import process_audit_exports
from apps.core.exports import csv_cell
from apps.organizations.models import OrganizationMembership
from apps.projects.tests.test_projects import PASSWORD, client_for, resources  # noqa: F401
from apps.usage.exports import process_usage_exports
from apps.usage.models import UsageEvent, UsageExport

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def event(service):
    return UsageEvent.objects.create(
        service=service,
        method="GET",
        outcome="allowed",
        units=3,
        latency_ms=5,
        decision={"allowed": True},
        status_code=200,
    )


def test_usage_daily_rollup_and_invalid_granularity(resources):
    owner, org, _, _, service = resources
    event(service)
    client = client_for(owner)
    path = f"/api/v1/organizations/{org.id}/usage/"
    response = client.get(path, {"granularity": "day"})
    assert response.status_code == 200 and response.data["data"]["granularity"] == "day"
    assert response.data["data"]["series"][0]["hour"].hour == 0
    assert response.data["data"]["series"][0]["units"] == 3
    assert client.get(path, {"granularity": "unbounded"}).status_code == 400


def test_reporting_and_exports_are_tenant_scoped(resources, settings, tmp_path):
    settings.EXPORT_ROOT = tmp_path
    owner, org, _, _, service = resources
    event(service)
    client = client_for(owner)
    base = f"/api/v1/organizations/{org.id}"
    response = client.get(base + "/usage/")
    assert response.status_code == 200 and response.data["data"]["summary"]["units"] == 3
    assert len(client.get(base + "/usage/events/").data["results"]) == 1
    assert client.get(base + "/audit-logs/").status_code == 200
    filters = {
        "start": (timezone.now() - timedelta(days=1)).isoformat(),
        "end": timezone.now().isoformat(),
    }
    for kind, processor, model in (
        ("usage", process_usage_exports, UsageExport),
        ("audit-logs", process_audit_exports, AuditExport),
    ):
        response = client.post(
            base + f"/{kind}/exports/", filters, format="json", HTTP_IDEMPOTENCY_KEY=kind
        )
        assert response.status_code == 202
        identifier = response.data["data"]["id"]
        path = base + f"/{kind}/exports/{identifier}/download/"
        assert client.get(path).status_code == 409
        assert processor() == 1
        assert processor() == 0
        response = client.get(path)
        assert response.status_code == 200 and response["Cache-Control"] == "no-store"
        content = b"".join(response.streaming_content).decode("utf-8-sig")
        assert "event_id" in content and "verifier" not in content
        outsider = User.objects.create_user(
            email=f"{kind}@example.com", password=PASSWORD, email_verified_at=timezone.now()
        )
        assert client_for(outsider).get(path).status_code == 404
        model.objects.filter(pk=identifier).update(expires_at=timezone.now() - timedelta(seconds=1))
        assert client.get(path).status_code == 409


def test_reporting_role_matrix_range_bounds_and_export_cap(resources, settings, tmp_path):
    settings.EXPORT_ROOT, settings.EXPORT_MAX_ROWS = tmp_path, 1
    owner, org, _, _, service = resources
    event(service)
    event(service)
    member = User.objects.create_user(
        email="analyst@example.com", password=PASSWORD, email_verified_at=timezone.now()
    )
    OrganizationMembership.objects.create(organization=org, user=member, role="analyst")
    client = client_for(member)
    base = f"/api/v1/organizations/{org.id}"
    assert client.get(base + "/usage/").status_code == 200
    assert (
        client.get(
            base + "/usage/", {"start": "2020-01-01T00:00:00Z", "end": timezone.now().isoformat()}
        ).status_code
        == 400
    )
    assert client.get(base + "/usage/", {"surprise": "ignored?"}).status_code == 400
    response = client.post(
        base + "/usage/exports/",
        {
            "start": (timezone.now() - timedelta(days=1)).isoformat(),
            "end": timezone.now().isoformat(),
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="bounded",
    )
    assert response.status_code == 202
    assert process_usage_exports() == 0
    row = UsageExport.objects.get()
    assert row.status == "failed" and row.failure_code == "export_row_limit"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("value", ["=1+1", " +SUM(A1)", "@formula", "-danger", "\ttext", "\rtext"])
def test_csv_formula_cells_are_escaped(value):
    assert csv_cell(value).startswith("'")


def test_export_io_failure_is_safe(resources, settings, tmp_path):
    settings.EXPORT_ROOT = tmp_path
    _, org, _, _, _ = resources
    row = UsageExport.objects.create(
        organization_id=org.id,
        actor_id=resources[0].id,
        filters={
            "start": (timezone.now() - timedelta(days=1)).isoformat(),
            "end": timezone.now().isoformat(),
        },
        expires_at=timezone.now() + timedelta(days=1),
    )
    with patch("apps.core.exports.tempfile.NamedTemporaryFile", side_effect=OSError("storage")):
        assert process_usage_exports() == 0
    row.refresh_from_db()
    assert row.status == "failed" and row.failure_code == "export_storage_unavailable"
