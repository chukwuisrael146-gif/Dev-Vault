import io
import json
from unittest.mock import patch
from uuid import uuid4

import pytest

from devvault_sdk import AccessDenied, Client, VerificationUnavailable


def client():
    return Client(
        base_url="https://devvault.example.com",
        service_id=str(uuid4()),
        environment="test",
        audience="orders",
        integration_secret="dvs_test_fixture",
    )


def response(code, body):
    stream = io.BytesIO(json.dumps(body).encode())
    stream.code = code
    return stream


def test_secure_configuration_and_secret_repr():
    configured = client()
    assert "dvs_test_fixture" not in repr(configured)
    with pytest.raises(ValueError):
        Client(
            base_url="http://example.com",
            service_id=str(uuid4()),
            environment="test",
            audience="orders",
            integration_secret="dvs_test",
        )


def test_allowed_response_and_headers():
    configured = client()
    body = {
        "data": {
            "allowed": True,
            "service_id": configured.service_id,
            "environment": "test",
            "audience": "orders",
            "key_id": str(uuid4()),
            "rate_limits": [],
            "quotas": [],
            "replayed": False,
        }
    }
    with patch("devvault_sdk.build_opener") as builder:
        builder.return_value.open.return_value = response(200, body)
        decision = configured.verify(
            api_key="dv_test_fixture", required_scopes=["orders:read"], request_id="one"
        )
    assert not decision.replayed
    request = builder.return_value.open.call_args.args[0]
    assert request.headers["X-devvault-service-token"] == "dvs_test_fixture"


@pytest.mark.parametrize(
    "code,body,error",
    [
        (200, {"data": {"allowed": False}}, VerificationUnavailable),
        (503, {"error": {}}, VerificationUnavailable),
        (302, {}, VerificationUnavailable),
        (429, {"error": {"code": "quota_exceeded", "details": {"retry_after": 3}}}, AccessDenied),
    ],
)
def test_denials_and_protocol_failures_are_closed(code, body, error):
    with patch("devvault_sdk.build_opener") as builder:
        builder.return_value.open.return_value = response(code, body)
        with pytest.raises(error):
            client().verify(api_key="dv_test_fixture", required_scopes=[], request_id="one")
