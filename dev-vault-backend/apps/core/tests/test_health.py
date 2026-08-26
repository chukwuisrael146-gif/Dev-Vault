from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.core.health import get_readiness_status


@pytest.mark.django_db
def test_liveness_is_minimal_and_carries_request_id(client) -> None:
    response = client.get(reverse("core:liveness"), HTTP_X_REQUEST_ID="test-request-123")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["X-Request-ID"] == "test-request-123"


@pytest.mark.django_db
@patch("apps.core.health.get_readiness_status", return_value=(False, ["redis"]))
def test_readiness_hides_dependency_details(_status, client) -> None:
    response = client.get(reverse("core:readiness"))

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "redis" not in response.content.decode()


@pytest.mark.django_db
def test_readiness_dependencies_pass_in_test_environment() -> None:
    ready, failed = get_readiness_status()

    assert ready is True
    assert failed == []
