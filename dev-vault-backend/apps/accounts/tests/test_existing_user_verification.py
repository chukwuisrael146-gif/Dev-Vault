from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import EmailVerificationToken, PasswordResetRequest, User
from apps.accounts.profile_services import request_password_reset
from apps.accounts.services import deliver_pending_verification_emails

pytestmark = pytest.mark.django_db


def test_active_unverified_account_can_verify_then_request_reset(mailoutbox):
    user = User.objects.create_user(
        email="existing@example.test",
        password="Birch-Lantern-174!River",
        status=User.Status.ACTIVE,
    )
    client = APIClient()
    request_password_reset(email=user.email)
    assert not PasswordResetRequest.objects.filter(user=user).exists()
    response = client.post(
        reverse("accounts:resend-verification"), {"email": user.email}, format="json"
    )
    assert response.status_code == 202
    assert EmailVerificationToken.objects.filter(user=user).count() == 1
    assert deliver_pending_verification_emails() == 1
    assert deliver_pending_verification_emails() == 0
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [user.email]
    user.refresh_from_db()
    assert user.email_verified_at is None  # Sending is not proof of ownership.
    link = next(line for line in mailoutbox[0].body.splitlines() if line.startswith("http"))
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    response = client.post(reverse("accounts:verify-email"), {"token": token}, format="json")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.email_is_verified and user.status == User.Status.ACTIVE
    assert (
        client.post(reverse("accounts:verify-email"), {"token": token}, format="json").status_code
        == 400
    )
    request_password_reset(email=user.email)
    assert PasswordResetRequest.objects.filter(user=user).count() == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"status": User.Status.DISABLED},
        {"is_active": False},
        {"email_verified_at": "verified"},
    ],
)
def test_existing_ineligible_account_resend_remains_generic(changes, mailoutbox):
    if changes.get("email_verified_at"):
        changes = {**changes, "email_verified_at": timezone.now()}
    user = User.objects.create_user(
        email="ineligible@example.test", password="Birch-Lantern-174!River", **changes
    )
    client = APIClient()
    url = reverse("accounts:resend-verification")
    response = client.post(url, {"email": user.email}, format="json")
    unknown = client.post(url, {"email": "unknown@example.test"}, format="json")
    assert response.status_code == unknown.status_code == 202
    assert response.data == unknown.data
    assert not EmailVerificationToken.objects.filter(user=user).exists()
    assert deliver_pending_verification_emails() == 0
    assert not mailoutbox
