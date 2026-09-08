from io import StringIO
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.core.checks import run_checks
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.access.rate_limits import consume_rates
from apps.core.exceptions import DependencyUnavailableError
from apps.core.idempotency import creation_command
from apps.projects.tests.test_projects import resources  # noqa: F401

pytestmark = pytest.mark.django_db


def test_schema_security_contract_and_validation():
    response = APIClient().get("/api/v1/schema/")
    assert response.status_code == 200
    schema = response.data
    verification = schema["paths"]["/api/v1/access/verify/"]["post"]
    assert verification["security"] == [{"ConsumerKey": [], "ServiceIntegration": []}]
    assert "DashboardAccess" in schema["components"]["securitySchemes"]
    keys = schema["paths"]["/api/v1/environments/{environment_id}/keys/"]["post"]
    assert any(p["name"] == "Idempotency-Key" and p["required"] for p in keys["parameters"])
    assert "201" in keys["responses"] and "200" in keys["responses"]
    assert APIClient().get("/api/v1/docs/").status_code == 200
    call_command("spectacular", validate=True, fail_on_warn=True, stdout=StringIO())


def test_json_payload_size_and_malformed_data():
    cache.clear()
    client = APIClient()
    assert (
        client.post("/api/v1/auth/login/", "x" * 65537, content_type="application/json").status_code
        == 413
    )
    assert (
        client.post("/api/v1/auth/login/", "{", content_type="application/json").status_code == 400
    )


def test_cors_exact_origin_and_no_browser_integration_header(settings):
    settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
    client = APIClient()
    response = client.options(
        "/api/v1/me/", HTTP_ORIGIN="http://localhost:5173", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET"
    )
    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "x-devvault-service-token" not in response["Access-Control-Allow-Headers"].lower()
    assert "Access-Control-Allow-Origin" not in client.options(
        "/api/v1/me/",
        HTTP_ORIGIN="https://evil.example.com",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )


def test_metrics_are_private_and_route_labels_are_bounded(settings):
    client = APIClient()
    assert client.get("/internal/metrics/").status_code == 404
    settings.METRICS_TOKEN = "metrics-fixture-" + "x" * 32
    client.get("/api/v1/health/live/")
    response = client.get(
        "/internal/metrics/", HTTP_AUTHORIZATION="Bearer " + settings.METRICS_TOKEN
    )
    assert response.status_code == 200 and b"devvault_http_requests_total" in response.content
    assert settings.METRICS_TOKEN.encode() not in response.content


def test_checks_management_commands_and_background_tasks():
    assert not [item for item in run_checks() if item.is_serious()]
    for command in (
        "deliver_account_emails",
        "deliver_verification_emails",
        "deliver_invitations",
        "aggregate_usage",
    ):
        call_command(command, stdout=StringIO())
    from apps.accounts.tasks import deliver_pending_resets, deliver_pending_verifications
    from apps.organizations.tasks import deliver_invitations
    from apps.usage.tasks import aggregate_usage
    from apps.webhooks.tasks import deliver_webhooks

    assert deliver_pending_resets() == 0
    assert deliver_pending_verifications() == 0
    assert deliver_invitations() == 0
    assert aggregate_usage() == 0
    assert deliver_webhooks() == 0


def test_enforcement_outage_and_incomplete_idempotency_fail_closed(resources):
    from uuid import uuid4

    _, _, _, _, service = resources
    with patch("apps.access.rate_limits._client") as client:
        client.return_value.ping.side_effect = ValueError("bad connection")
        with pytest.raises(DependencyUnavailableError):
            consume_rates(policies=[], key=None, service=service)
    with (
        pytest.raises(RuntimeError, match="record its result"),
        creation_command(actor_id=uuid4(), scope="test", key="incomplete", values={}),
    ):
        pass
