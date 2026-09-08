import json
import socket
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.core.exceptions import DomainError
from apps.credentials.services import issue_key
from apps.projects.tests.test_projects import client_for, resources  # noqa: F401
from apps.webhooks.crypto import cipher, signature
from apps.webhooks.models import DeliveryAttempt, WebhookDelivery
from apps.webhooks.services import create_endpoint, deliver_one
from apps.webhooks.transport import UnsafeDestination, destination, post_json, public_address

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def queued(resources):
    owner, org, _, _, service = resources
    endpoint, secret, _ = create_endpoint(
        actor=owner,
        organization_id=org.id,
        url="https://hooks.example.com/devvault",
        event_types=["key.created"],
        idempotency_key="endpoint",
    )
    issued = issue_key(
        actor=owner, service_id=service.id, name="Consumer", idempotency_key="consumer"
    )
    return owner, org, endpoint, secret, issued, WebhookDelivery.objects.get()


def test_signed_delivery_is_durable_secret_safe_and_idempotent(queued, settings):
    owner, org, endpoint, secret, issued, delivery = queued
    assert (
        secret != endpoint.encrypted_secret
        and cipher().decrypt(endpoint.encrypted_secret.encode()).decode() == secret
    )
    assert secret not in json.dumps(delivery.payload) and issued.raw_value not in json.dumps(
        delivery.payload
    )
    assert deliver_one(delivery.id) is False
    settings.WEBHOOK_DELIVERY_ENABLED = True
    with patch("apps.webhooks.services.post_json", return_value=204) as sender:
        assert deliver_one(delivery.id)
        assert not deliver_one(delivery.id)
    assert sender.call_count == 1
    _, body, headers = sender.call_args.args
    timestamp = headers["X-DevVault-Signature"].split(",")[0][2:]
    assert headers["X-DevVault-Signature"] == signature(
        secret=secret, timestamp=int(timestamp), body=body
    )
    assert DeliveryAttempt.objects.count() == 1
    client = client_for(owner)
    path = f"/api/v1/organizations/{org.id}/webhooks/"
    response = client.post(
        path,
        {"url": endpoint.url, "event_types": endpoint.event_types},
        format="json",
        HTTP_IDEMPOTENCY_KEY="endpoint",
    )
    assert response.status_code == 200 and "secret" not in response.data["data"]
    assert "encrypted_secret" not in client.get(path).data["results"][0]


@pytest.mark.parametrize(
    "result,status",
    [(500, "pending"), (429, "pending"), (301, "dead_letter"), (400, "dead_letter")],
)
def test_retries_do_not_follow_redirects(queued, settings, result, status):
    settings.WEBHOOK_DELIVERY_ENABLED = True
    row = queued[-1]
    with patch("apps.webhooks.services.post_json", return_value=result):
        assert not deliver_one(row.id)
    row.refresh_from_db()
    assert row.attempts == 1 and row.status == status
    assert row.last_status_code == result


def test_unsafe_destination_dead_letter_and_secret_rotation(queued, settings):
    settings.WEBHOOK_DELIVERY_ENABLED = True
    owner, org, endpoint, old_secret, _, row = queued
    with patch("apps.webhooks.services.post_json", side_effect=UnsafeDestination):
        assert not deliver_one(row.id)
    row.refresh_from_db()
    assert row.status == "dead_letter" and row.last_error_code == "unsafe_destination"
    client = client_for(owner)
    path = f"/api/v1/organizations/{org.id}/webhooks/{endpoint.id}/rotate-secret/"
    result = client.post(path, {"confirm": True}, format="json", HTTP_IDEMPOTENCY_KEY="rotate")
    assert result.status_code == 200 and result.data["data"]["secret"] != old_secret
    assert (
        "secret"
        not in client.post(
            path, {"confirm": True}, format="json", HTTP_IDEMPOTENCY_KEY="rotate"
        ).data["data"]
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/?token=abc",
        "https://example.com/#frag",
        "https://example.com:8443",
        "https://example.com/\r\nHeader:bad",
    ],
)
def test_callback_url_restrictions(url):
    with pytest.raises(DomainError):
        destination(url)


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.1", "::1", "fc00::1", "224.0.0.1"],
)
def test_ssrf_private_and_special_addresses_are_blocked(address):
    with (
        patch(
            "socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))],
        ),
        pytest.raises(UnsafeDestination),
    ):
        public_address("hooks.example.com")


def test_dns_address_is_pinned_to_connection_and_tls_host_preserved():
    with (
        patch("apps.webhooks.transport.public_address", return_value="93.184.216.34"),
        patch("apps.webhooks.transport.PinnedHTTPSConnection") as connection,
    ):
        connection.return_value.getresponse.return_value.status = 204
        assert post_json("https://hooks.example.com/events", b"{}", {}) == 204
    connection.assert_called_once_with("hooks.example.com", "93.184.216.34")
    assert connection.return_value.request.call_args.args[:2] == ("POST", "/events")


def test_outbox_creation_rolls_back_with_security_mutation(resources):
    owner, org, _, _, service = resources
    create_endpoint(
        actor=owner,
        organization_id=org.id,
        url="https://hooks.example.com",
        event_types=["key.created"],
        idempotency_key="hook",
    )
    with (
        patch(
            "apps.webhooks.services.WebhookDelivery.objects.get_or_create",
            side_effect=RuntimeError("outbox"),
        ),
        pytest.raises(RuntimeError),
    ):
        issue_key(actor=owner, service_id=service.id, name="Rollback", idempotency_key="rollback")
    from apps.credentials.models import APIKey

    assert APIKey.objects.count() == 0
