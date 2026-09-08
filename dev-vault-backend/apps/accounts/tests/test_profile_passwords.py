import re
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.auth_services import login_user, refresh_session
from apps.accounts.exceptions import InvalidSessionTokenError
from apps.accounts.models import PasswordResetRequest, RefreshTokenSession, User
from apps.accounts.profile_services import (
    InvalidPasswordReset,
    change_password,
    deliver_pending_password_resets,
    password_reset_token,
    request_password_reset,
    reset_password,
)
from apps.audit.models import AuditLog
from apps.core.logging import REDACTED, redact_string, redact_value

pytestmark = pytest.mark.django_db
OLD = "Birch-Meadow-615!River"
NEW = "Maple-Trail-327!Ocean"


@pytest.fixture
def user():
    return User.objects.create_user(
        email="profile@example.com",
        password=OLD,
        email_verified_at=timezone.now(),
        first_name="Original",
    )


@pytest.fixture
def client(user):
    _, pair = login_user(email=user.email, password=OLD)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + pair.access_token)
    return client


def test_current_user_profile_is_self_scoped_and_safe(user, client):
    assert APIClient().get("/api/v1/me/").status_code == 401
    response = client.get("/api/v1/me/")
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response.data["data"]["user"]["id"] == str(user.id)
    assert "password" not in response.data["data"]["user"]
    assert client.patch("/api/v1/me/", {"first_name": "Updated"}, format="json").status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Updated"
    assert AuditLog.objects.filter(action="account.profile_updated", actor_id=user.id).exists()
    for field in ("email", "status", "is_staff", "id", "password"):
        assert client.patch("/api/v1/me/", {field: "forbidden"}, format="json").status_code == 400


def test_password_change_revokes_all_sessions(user, client):
    _, second = login_user(email=user.email, password=OLD)
    response = client.post(
        "/api/v1/me/password/",
        {
            "current_password": OLD,
            "new_password": NEW,
            "password_confirmation": NEW,
        },
        format="json",
    )
    assert response.status_code == 200
    assert client.get("/api/v1/me/").status_code == 401
    with pytest.raises(InvalidSessionTokenError):
        refresh_session(refresh_token=second.refresh_token)
    user.refresh_from_db()
    assert user.check_password(NEW)
    assert not RefreshTokenSession.objects.filter(user=user, revoked_at__isnull=True).exists()


@pytest.mark.parametrize(
    "password,confirmation,current,expected",
    [
        (NEW, NEW, "wrong", 401),
        (NEW, "mismatch", OLD, 400),
        ("password", "password", OLD, 400),
        (OLD, OLD, OLD, 400),
        ("x" * 1025, "x" * 1025, OLD, 400),
    ],
)
def test_password_change_rejects_bad_input(user, client, password, confirmation, current, expected):
    response = client.post(
        "/api/v1/me/password/",
        {
            "current_password": current,
            "new_password": password,
            "password_confirmation": confirmation,
        },
        format="json",
    )
    assert response.status_code == expected
    user.refresh_from_db()
    assert user.check_password(OLD)


def test_reset_request_generic_response_and_cooldown(user):
    client = APIClient()
    responses = [
        client.post(reverse("accounts:password-reset"), {"email": email}, format="json")
        for email in (user.email, "unknown@example.com", user.email)
    ]
    assert all(r.status_code == 202 for r in responses)
    assert responses[0].data == responses[1].data == responses[2].data
    assert PasswordResetRequest.objects.count() == 1
    row = PasswordResetRequest.objects.get()
    PasswordResetRequest.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - timedelta(minutes=2)
    )
    request_password_reset(email=user.email)
    row.refresh_from_db()
    assert row.invalidated_at is not None


def test_reset_outbox_and_single_use(user, mailoutbox, client):
    request_password_reset(email=user.email)
    assert not mailoutbox
    assert deliver_pending_password_resets() == 1
    assert deliver_pending_password_resets() == 0
    link = re.search(r"https?://\S+", mailoutbox[0].body).group()
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    response = APIClient().post(
        reverse("accounts:password-reset-confirm"),
        {
            "token": token,
            "new_password": NEW,
            "password_confirmation": NEW,
        },
        format="json",
    )
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert client.get("/api/v1/me/").status_code == 401
    assert PasswordResetRequest.objects.get().consumed_at is not None
    with pytest.raises(InvalidPasswordReset):
        reset_password(token=token, new_password="Another-Strong-894!Password")
    assert AuditLog.objects.filter(action="account.password_reset_completed").count() == 1
    assert token not in str(list(AuditLog.objects.values()))
    assert redact_string(token) == REDACTED
    assert redact_value({"new_password": NEW, "current_password": OLD}) == {
        "new_password": REDACTED,
        "current_password": REDACTED,
    }


@pytest.mark.parametrize(
    "change", ["expired", "disabled", "inactive", "password", "email", "tamper"]
)
def test_reset_denies_expiry_and_credential_changes(user, change):
    request_password_reset(email=user.email)
    row = PasswordResetRequest.objects.get()
    token = password_reset_token(row)
    if change == "expired":
        row.expires_at = timezone.now()
        row.save()
    elif change == "disabled":
        user.status = User.Status.DISABLED
    elif change == "inactive":
        user.is_active = False
    elif change == "password":
        user.set_password("Changed-Password-894!Ocean")
    elif change == "email":
        user.email = "changed@example.com"
    else:
        token += "tampered"
    user.save()
    with pytest.raises(InvalidPasswordReset):
        reset_password(token=token, new_password=NEW)
    row.refresh_from_db()
    assert row.consumed_at is None


def test_reset_email_retries_after_delivery_failure(user, mailoutbox):
    request_password_reset(email=user.email)
    with patch("apps.accounts.profile_services.EmailMessage.send", side_effect=OSError("offline")):
        assert deliver_pending_password_resets() == 0
    row = PasswordResetRequest.objects.get()
    assert row.delivery_attempts == 1
    assert row.sent_at is None
    assert row.next_attempt_at > timezone.now()
    PasswordResetRequest.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
    assert deliver_pending_password_resets() == 1
    assert len(mailoutbox) == 1


def test_password_mutations_rollback_on_audit_failure(user, client):
    request_password_reset(email=user.email)
    row = PasswordResetRequest.objects.get()
    token = password_reset_token(row)
    for operation in (
        lambda: change_password(actor=user, current_password=OLD, new_password=NEW),
        lambda: reset_password(token=token, new_password=NEW),
    ):
        with (
            patch("apps.accounts.profile_services.record_event", side_effect=RuntimeError("audit")),
            pytest.raises(RuntimeError),
        ):
            operation()
    user.refresh_from_db()
    row.refresh_from_db()
    assert user.check_password(OLD)
    assert row.consumed_at is None and row.invalidated_at is None
    assert client.get("/api/v1/me/").status_code == 200


def test_local_preview_decodes_quoted_printable_links(user, settings, tmp_path):
    settings.BASE_DIR = tmp_path
    settings.MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.filebased.EmailBackend",
            "OPTIONS": {"file_path": tmp_path / "var" / "emails"},
        }
    }
    request_password_reset(email=user.email)
    assert deliver_pending_password_resets() == 1
    output = StringIO()
    with patch(
        "apps.accounts.management.commands.preview_email.webbrowser.open", return_value=True
    ) as browser:
        call_command("preview_email", open=True, stdout=output)
    link = browser.call_args.args[0]
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    assert token.startswith("dv_reset_")
    assert token not in output.getvalue()
    reset_password(token=token, new_password=NEW)
    user.refresh_from_db()
    assert user.check_password(NEW)


def test_preview_requires_file_mailer_and_reset_page_has_safe_headers():
    with pytest.raises(CommandError):
        call_command("preview_email", stdout=StringIO())
    response = APIClient().get(reverse("accounts:password-reset-confirm"))
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
