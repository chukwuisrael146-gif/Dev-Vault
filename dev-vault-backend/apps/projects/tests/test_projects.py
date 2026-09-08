from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.auth_services import login_user
from apps.accounts.models import User
from apps.core.exceptions import DomainError
from apps.organizations.models import OrganizationMembership
from apps.organizations.services import create_organization
from apps.projects.models import APIService, Environment, Project
from apps.projects.services import create_project, create_service

pytestmark = pytest.mark.django_db
PASSWORD = "Forest-Meadow-978!Stone"


def client_for(user):
    _, pair = login_user(email=user.email, password=PASSWORD)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + pair.access_token)
    return client


@pytest.fixture
def resources():
    owner = User.objects.create_user(
        email="projectowner@example.com", password=PASSWORD, email_verified_at=timezone.now()
    )
    organization, _ = create_organization(
        actor=owner, name="Acme", slug="acme", idempotency_key="acme"
    )
    project, _ = create_project(
        actor=owner, organization_id=organization.id, name="API", slug="api", idempotency_key="api"
    )
    environment = Environment.objects.get(project=project, kind="test")
    service, _ = create_service(
        actor=owner,
        environment_id=environment.id,
        name="Orders",
        slug="orders",
        audience="orders-api",
        idempotency_key="orders",
    )
    return owner, organization, project, environment, service


def test_canonical_environments_and_retry(resources):
    owner, organization, project, environment, service = resources
    assert set(Environment.objects.filter(project=project).values_list("kind", flat=True)) == {
        "test",
        "live",
    }
    same, created = create_project(
        actor=owner, organization_id=organization.id, name="API", slug="api", idempotency_key="api"
    )
    assert same.id == project.id and not created
    assert Environment.objects.count() == 2
    client = client_for(owner)
    assert len(client.get(f"/api/v1/projects/{project.id}/environments/").data["data"]) == 2
    assert (
        client.get(f"/api/v1/services/{service.id}/").data["data"]["environment_id"]
        == environment.id
    )


def test_cross_tenant_and_immutable_parent_inputs(resources):
    owner, organization, project, environment, service = resources
    outsider = User.objects.create_user(
        email="other@example.com", password=PASSWORD, email_verified_at=timezone.now()
    )
    client = client_for(outsider)
    for path in (
        f"organizations/{organization.id}/projects/",
        f"projects/{project.id}/",
        f"projects/{project.id}/environments/",
        f"environments/{environment.id}/services/",
        f"services/{service.id}/",
    ):
        assert client.get("/api/v1/" + path).status_code == 404
    assert (
        client.post(
            f"/api/v1/services/{service.id}/status/",
            {"is_active": False, "confirm": True},
            format="json",
        ).status_code
        == 404
    )
    client = client_for(owner)
    assert (
        client.patch(
            f"/api/v1/projects/{project.id}/",
            {"name": "Moved", "organization_id": str(organization.id)},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/v1/environments/{environment.id}/services/",
            {
                "name": "Injected",
                "slug": "injected",
                "audience": "injected",
                "environment_id": str(environment.id),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="injected",
        ).status_code
        == 400
    )


@pytest.mark.parametrize("role", ["admin", "developer", "analyst", "billing"])
def test_project_and_live_service_role_matrix(resources, role):
    owner, organization, project, environment, service = resources
    member = User.objects.create_user(
        email=f"{role}@example.com", password=PASSWORD, email_verified_at=timezone.now()
    )
    OrganizationMembership.objects.create(organization=organization, user=member, role=role)
    client = client_for(member)
    response = client.post(
        f"/api/v1/organizations/{organization.id}/projects/",
        {
            "name": "Another",
            "slug": "another",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="another",
    )
    assert response.status_code == (201 if role in {"admin", "developer"} else 403)
    live = Environment.objects.get(project=project, kind="live")
    response = client.post(
        f"/api/v1/environments/{live.id}/services/",
        {
            "name": "Production",
            "slug": "production",
            "audience": "production-api",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="production",
    )
    assert response.status_code == (201 if role == "admin" else 403)


def test_service_disable_project_archive_and_atomic_creation(resources):
    owner, organization, project, environment, service = resources
    client = client_for(owner)
    response = client.post(
        f"/api/v1/services/{service.id}/status/",
        {"is_active": False, "confirm": True},
        format="json",
    )
    assert response.status_code == 200
    service.refresh_from_db()
    assert not service.is_active
    with (
        patch("apps.projects.services.record_event", side_effect=RuntimeError("audit")),
        pytest.raises(RuntimeError),
    ):
        create_project(
            actor=owner,
            organization_id=organization.id,
            name="Rollback",
            slug="rollback",
            idempotency_key="rollback",
        )
    assert Project.objects.count() == 1
    assert Environment.objects.count() == 2
    assert APIService.objects.count() == 1
    assert (
        client.post(
            f"/api/v1/projects/{project.id}/archive/", {"confirm": True}, format="json"
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/services/{service.id}/status/",
            {"is_active": True, "confirm": True},
            format="json",
        ).status_code
        == 403
    )
    with pytest.raises(DomainError):
        create_service(
            actor=owner,
            environment_id=environment.id,
            name="Forbidden",
            slug="forbidden",
            audience="forbidden",
            idempotency_key="forbidden",
        )
