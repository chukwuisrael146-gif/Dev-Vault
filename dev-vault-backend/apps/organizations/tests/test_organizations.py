from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.auth_services import login_user
from apps.accounts.models import RefreshTokenSession, User
from apps.audit.models import AuditLog
from apps.core.exceptions import DomainError
from apps.core.models import IdempotencyRecord
from apps.organizations.models import Organization, OrganizationMembership
from apps.organizations.permissions import CAPABILITIES, require_capability
from apps.organizations.services import (
    accept_invitation,
    create_organization,
    deliver_pending_invitations,
    invitation_token,
    invite_member,
)

pytestmark = pytest.mark.django_db
PASSWORD = "Forest-Cedar-938!Breeze"


def account(email):
    return User.objects.create_user(
        email=email, password=PASSWORD, email_verified_at=timezone.now()
    )


def api(user):
    _, tokens = login_user(email=user.email, password=PASSWORD)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + tokens.access_token)
    return client


@pytest.fixture
def owner():
    return account("owner@example.com")


@pytest.fixture
def organization(owner):
    return create_organization(
        actor=owner, name="Testing", slug="testing", idempotency_key="org-first"
    )[0]


def test_create_idempotency_and_rollback(owner):
    client = api(owner)
    body = {"name": "Example", "slug": "example"}
    assert client.post("/api/v1/organizations/", body, format="json").status_code == 400
    first = client.post("/api/v1/organizations/", body, format="json", HTTP_IDEMPOTENCY_KEY="one")
    repeated = client.post(
        "/api/v1/organizations/", body, format="json", HTTP_IDEMPOTENCY_KEY="one"
    )
    assert (first.status_code, repeated.status_code) == (201, 200)
    assert first.data == repeated.data
    assert Organization.objects.count() == 1
    assert OrganizationMembership.objects.get().role == "owner"
    assert (
        client.post(
            "/api/v1/organizations/",
            {"name": "Other", "slug": "other"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="one",
        ).status_code
        == 409
    )
    with (
        patch("apps.organizations.services.record_event", side_effect=RuntimeError("audit")),
        pytest.raises(RuntimeError),
    ):
        create_organization(actor=owner, name="Rollback", slug="rollback", idempotency_key="two")
    assert not Organization.objects.filter(slug="rollback").exists()
    assert IdempotencyRecord.objects.count() == 1


def test_cross_tenant_routes_do_not_reveal_resources(owner, organization):
    outsider = api(account("outsider@example.com"))
    prefix = f"/api/v1/organizations/{organization.id}/"
    assert outsider.get("/api/v1/organizations/").data["results"] == []
    assert outsider.get(prefix).status_code == 404
    assert outsider.get(prefix + "members/").status_code == 404
    assert outsider.patch(prefix, {"name": "Hacked"}, format="json").status_code == 404
    assert (
        outsider.post(
            prefix + "invitations/",
            {"email": "intruder@example.com", "role": "admin"},
            format="json",
        ).status_code
        == 404
    )
    assert outsider.post(prefix + "archive/", {"confirm": True}, format="json").status_code == 404
    assert (
        outsider.post(
            prefix + "transfer-ownership/",
            {"membership_id": str(uuid4()), "confirm": True},
            format="json",
        ).status_code
        == 404
    )
    organization.refresh_from_db()
    assert organization.name == "Testing" and organization.status == "active"


@pytest.mark.parametrize("role", ["admin", "developer", "analyst", "billing"])
def test_roles_cannot_change_organization_ownership_or_name(owner, organization, role):
    member = account(role + "@example.com")
    membership = OrganizationMembership.objects.create(
        organization=organization, user=member, role=role
    )
    client = api(member)
    prefix = f"/api/v1/organizations/{organization.id}/"
    assert client.get(prefix).status_code == 200
    assert client.patch(prefix, {"name": "Forbidden"}, format="json").status_code == 403
    assert client.post(prefix + "archive/", {"confirm": True}, format="json").status_code == 403
    assert (
        client.post(
            prefix + "transfer-ownership/",
            {"membership_id": str(membership.id), "confirm": True},
            format="json",
        ).status_code
        == 403
    )
    expected = 201 if role == "admin" else 403
    assert (
        client.post(
            prefix + "invitations/",
            {"email": "invitee@example.com", "role": "analyst"},
            format="json",
        ).status_code
        == expected
    )


def test_last_owner_protection_recent_login_and_transfer(owner, organization):
    client = api(owner)
    member = OrganizationMembership.objects.get(user=owner)
    prefix = f"/api/v1/organizations/{organization.id}/"
    member_url = prefix + f"members/{member.id}/"
    assert client.patch(member_url, {"role": "developer"}, format="json").status_code == 409
    assert client.post(member_url + "remove/", {"confirm": True}, format="json").status_code == 409
    assert client.post(prefix + "archive/", {"confirm": False}, format="json").status_code == 400
    other = account("successor@example.com")
    target = OrganizationMembership.objects.create(
        organization=organization, user=other, role="developer"
    )
    assert (
        client.post(
            prefix + "transfer-ownership/",
            {"membership_id": str(target.id), "confirm": True},
            format="json",
        ).status_code
        == 204
    )
    member.refresh_from_db()
    target.refresh_from_db()
    assert (member.role, target.role) == ("admin", "owner")
    new_owner = api(other)
    RefreshTokenSession.objects.filter(user=other).update(
        created_at=timezone.now() - timedelta(minutes=16)
    )
    response = new_owner.post(prefix + "archive/", {"confirm": True}, format="json")
    assert response.status_code == 400
    assert response.data["error"]["code"] == "recent_authentication_required"


def test_invitation_email_binding_single_use_and_audit(owner, organization, mailoutbox):
    invitee = account("invitee@example.com")
    invitation = invite_member(
        actor=owner, organization_id=organization.id, email=invitee.email, role="developer"
    )
    token = invitation_token(invitation)
    assert deliver_pending_invitations() == 1
    assert deliver_pending_invitations() == 0
    assert token in mailoutbox[0].body
    with pytest.raises(DomainError):
        accept_invitation(actor=account("wrong@example.com"), token=token)
    member = accept_invitation(actor=invitee, token=token)
    assert member.role == "developer"
    with pytest.raises(DomainError):
        accept_invitation(actor=invitee, token=token)
    events = AuditLog.objects.filter(organization_id=organization.id)
    assert events.filter(action="organization.member_joined", actor_id=invitee.id).exists()
    assert token not in str(list(events.values()))


def test_invitation_loses_authority_when_inviter_removed(owner, organization):
    admin = account("admin@example.com")
    membership = OrganizationMembership.objects.create(
        organization=organization, user=admin, role="admin"
    )
    invitee = account("pending@example.com")
    invitation = invite_member(
        actor=admin, organization_id=organization.id, email=invitee.email, role="developer"
    )
    membership.is_active = False
    membership.save()
    with pytest.raises(DomainError):
        accept_invitation(actor=invitee, token=invitation_token(invitation))


def test_capability_matrix_is_deny_by_default():
    assert "key" not in CAPABILITIES["analyst"]
    assert "ownership" not in CAPABILITIES["developer"]
    assert "live_key" not in CAPABILITIES["developer"]
    with pytest.raises(DomainError):
        require_capability("unknown", "read")
    with pytest.raises(DomainError):
        require_capability("owner", "unknown")
