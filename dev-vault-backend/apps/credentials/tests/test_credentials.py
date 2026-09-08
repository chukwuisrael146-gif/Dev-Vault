from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import DomainError
from apps.credentials.hashing import InvalidCredential
from apps.credentials.models import APIKey
from apps.credentials.services import authenticate_integration, authenticate_key, issue_key
from apps.organizations.models import OrganizationMembership
from apps.projects.models import Environment
from apps.projects.services import create_service
from apps.projects.tests.test_projects import PASSWORD, client_for, resources  # noqa: F401

pytestmark = pytest.mark.django_db


def issue(client, environment, service, command="create", **extra):
    return client.post(
        f"/api/v1/environments/{environment.id}/keys/",
        {"name": "Consumer", "service_id": str(service.id), **extra},
        format="json",
        HTTP_IDEMPOTENCY_KEY=command,
    )


def test_one_time_secret_and_idempotent_retry(resources):
    owner, _, _, environment, service = resources
    client = client_for(owner)
    response = issue(client, environment, service)
    assert response.status_code == 201
    assert response["Cache-Control"] == "no-store"
    data = response.data["data"]
    key = APIKey.objects.get(pk=data["id"])
    assert data["secret"].startswith("dv_test_")
    assert data["secret"] not in repr(key.__dict__)
    assert authenticate_key(raw=data["secret"], service=service).id == key.id
    retry = issue(client, environment, service)
    assert retry.status_code == 200 and "secret" not in retry.data["data"]
    assert APIKey.objects.count() == 1
    detail = client.get(f"/api/v1/keys/{key.id}/")
    assert not {"secret", "verifier", "pepper_version"} & set(detail.data["data"])
    assert issue(client, environment, service, name="Changed").status_code == 409
    assert issue(client, environment, service, command="").status_code == 400


def test_rotation_overlap_and_revocation(resources):
    owner, _, _, environment, service = resources
    client = client_for(owner)
    first = issue(client, environment, service).data["data"]
    path = f"/api/v1/keys/{first['id']}/rotate/"
    response = client.post(
        path, {"confirm": True, "overlap_seconds": 60}, format="json", HTTP_IDEMPOTENCY_KEY="rotate"
    )
    assert response.status_code == 201
    second = response.data["data"]
    old, new = APIKey.objects.get(pk=first["id"]), APIKey.objects.get(pk=second["id"])
    assert old.family_id == new.family_id and old.successor_id == new.id
    assert old.expires_at < new.expires_at
    authenticate_key(raw=first["secret"], service=service)
    authenticate_key(raw=second["secret"], service=service)
    assert (
        "secret"
        not in client.post(
            path,
            {"confirm": True, "overlap_seconds": 60},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rotate",
        ).data["data"]
    )
    response = client.post(f"/api/v1/keys/{second['id']}/revoke/", {"confirm": True}, format="json")
    assert response.status_code == 200
    with pytest.raises(InvalidCredential, match="credential"):
        authenticate_key(raw=second["secret"], service=service)


def test_credential_types_and_service_boundaries(resources):
    owner, _, project, environment, service = resources
    client = client_for(owner)
    data = issue(client, environment, service).data["data"]
    response = client.post(
        f"/api/v1/services/{service.id}/integration-credentials/",
        {"name": "Backend"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="backend",
    )
    assert response.status_code == 201
    integration = response.data["data"]
    assert authenticate_integration(integration["secret"]).service_id == service.id
    with pytest.raises(InvalidCredential):
        authenticate_integration(data["secret"])
    with pytest.raises(InvalidCredential):
        authenticate_key(raw=integration["secret"], service=service)
    live = Environment.objects.get(project=project, kind="live")
    assert issue(client, live, service, command="wrong-parent").status_code == 404
    live_service, _ = create_service(
        actor=owner,
        environment_id=live.id,
        name="Live",
        slug="live",
        audience="live-api",
        idempotency_key="live",
    )
    with pytest.raises(InvalidCredential):
        authenticate_key(raw=data["secret"], service=live_service)
    assert (
        client.post(
            f"/api/v1/services/{service.id}/integration-credentials/{integration['id']}/revoke/",
            {"confirm": True},
            format="json",
        ).status_code
        == 204
    )
    with pytest.raises(InvalidCredential):
        authenticate_integration(integration["secret"])


@pytest.mark.parametrize("role", ["admin", "developer", "analyst", "billing"])
def test_key_role_matrix_and_tenant_isolation(resources, role):
    owner, organization, project, environment, service = resources
    member = User.objects.create_user(
        email=f"{role}@example.com", password=PASSWORD, email_verified_at=timezone.now()
    )
    client = client_for(member)
    assert issue(client, environment, service).status_code == 404
    OrganizationMembership.objects.create(organization=organization, user=member, role=role)
    assert issue(client, environment, service).status_code == (
        201 if role in {"admin", "developer"} else 403
    )
    live = Environment.objects.get(project=project, kind="live")
    live_service, _ = create_service(
        actor=owner,
        environment_id=live.id,
        name="Live",
        slug="live",
        audience="live-api",
        idempotency_key="live",
    )
    assert issue(client, live, live_service, command="live").status_code == (
        201 if role == "admin" else 403
    )


def test_pepper_version_expiry_tamper_and_audit_atomicity(resources, settings):
    owner, _, _, environment, service = resources
    settings.API_KEY_PEPPERS = {"a": "a" * 40, "b": "b" * 40}
    settings.API_KEY_ACTIVE_PEPPER_VERSION = "a"
    issued = issue_key(actor=owner, service_id=service.id, name="Key", idempotency_key="key")
    settings.API_KEY_ACTIVE_PEPPER_VERSION = "b"
    assert authenticate_key(raw=issued.raw_value, service=service).id == issued.resource.id
    with pytest.raises(InvalidCredential):
        authenticate_key(raw=issued.raw_value[:-2] + "XX", service=service)
    settings.API_KEY_PEPPERS = {"b": "b" * 40}
    with pytest.raises(InvalidCredential):
        authenticate_key(raw=issued.raw_value, service=service)
    with pytest.raises(DomainError):
        issue_key(
            actor=owner,
            service_id=service.id,
            name="Key",
            idempotency_key="past",
            expires_at=timezone.now() - timedelta(seconds=1),
        )
    with (
        patch("apps.credentials.services.record_event", side_effect=RuntimeError("audit")),
        pytest.raises(RuntimeError),
    ):
        issue_key(actor=owner, service_id=service.id, name="Key", idempotency_key="rollback")
    assert APIKey.objects.count() == 1
