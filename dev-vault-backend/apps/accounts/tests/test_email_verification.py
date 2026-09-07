import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, connection, connections, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.exceptions import InvalidEmailVerificationError
from apps.accounts.models import EmailVerificationToken, User
from apps.accounts.services import (
    deliver_pending_verification_emails,
    deliver_verification_email,
    register_user,
    request_email_verification,
    verify_email,
)
from apps.accounts.tokens import make_verification_token
from apps.audit.models import AuditLog
from apps.core.logging import REDACTED, redact_string, redact_value

pytestmark = pytest.mark.django_db


@pytest.fixture
def pending():
    user = register_user(email="pending@example.com", password="Cedar-Lantern-581!Fox")
    verification = EmailVerificationToken.objects.get(user=user)
    token = make_verification_token(verification_id=verification.id, user=user)
    return user, verification, token


def post_token(token):
    return APIClient().post(reverse("accounts:verify-email"), {"token": token}, format="json")


def age_request(verification):
    EmailVerificationToken.objects.filter(pk=verification.pk).update(
        created_at=timezone.now() - timedelta(minutes=2),
    )


def test_registration_queues_mail_until_delivered_and_verifies(pending, mailoutbox):
    user, verification, _ = pending
    assert mailoutbox == []
    assert deliver_pending_verification_emails() == 1
    assert deliver_pending_verification_emails() == 0
    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.to == [user.email]
    link = re.search(r"http://[^\s]+", message.body).group()
    parsed = urlsplit(link)
    assert parsed.netloc == "127.0.0.1:8000"
    assert parsed.query == ""
    token = parse_qs(parsed.fragment)["token"][0]
    response = post_token(token)
    assert response.status_code == 200
    assert token not in str(response.data)
    user.refresh_from_db()
    verification.refresh_from_db()
    assert user.email_verified_at is not None
    assert user.can_authenticate is True
    assert verification.consumed_at is not None
    assert post_token(token).status_code == 400
    assert AuditLog.objects.filter(action="account.email_verified", target_id=user.id).count() == 1


@pytest.mark.parametrize("change", ["expired", "disabled", "inactive", "email", "password"])
def test_link_cannot_verify_changed_or_expired_account(pending, change):
    user, verification, token = pending
    if change == "expired":
        verification.expires_at = timezone.now()
        verification.save()
    elif change == "disabled":
        user.status = User.Status.DISABLED
    elif change == "inactive":
        user.is_active = False
    elif change == "email":
        user.email = "changed@example.com"
    elif change == "password":
        user.set_password("Changed-Cedar-872!")
    user.save()
    response = post_token(token)
    assert response.status_code == 400
    assert response.data["error"]["code"] == "invalid_verification_token"
    assert token not in str(response.data)
    user.refresh_from_db()
    assert user.email_verified_at is None


def test_tampered_unknown_and_wrong_user_tokens_fail(pending):
    user, verification, token = pending
    other = User.objects.create_user(email="other@example.com", password="Another-Password-17!")
    bad_tokens = [
        "not-a-token",
        token + "tampered",
        "dv_verify_" + str(uuid.uuid4()) + ":bad",
        make_verification_token(verification_id=verification.id, user=other),
    ]
    for bad_token in bad_tokens:
        response = post_token(bad_token)
        assert response.status_code == 400
        assert response.data["error"]["code"] == "invalid_verification_token"
    user.refresh_from_db()
    assert user.email_verified_at is None


def test_resend_is_generic_and_enforces_cooldown(pending):
    user, verification, _ = pending
    client = APIClient()
    url = reverse("accounts:resend-verification")
    known = client.post(url, {"email": user.email}, format="json")
    unknown = client.post(url, {"email": "unknown@example.com"}, format="json")
    user.status = User.Status.DISABLED
    user.save()
    disabled = client.post(url, {"email": user.email}, format="json")
    assert known.status_code == unknown.status_code == disabled.status_code == 202
    assert known.data == unknown.data == disabled.data
    assert EmailVerificationToken.objects.count() == 1
    assert not User.objects.filter(email="unknown@example.com").exists()


def test_resend_invalidates_old_link_and_keeps_only_one_open_record(pending):
    user, verification, token = pending
    age_request(verification)
    request_email_verification(email="PENDING@EXAMPLE.COM")
    verification.refresh_from_db()
    assert verification.invalidated_at is not None
    assert post_token(token).status_code == 400
    current = EmailVerificationToken.objects.get(user=user, invalidated_at__isnull=True)
    assert current.id != verification.id
    new_token = make_verification_token(verification_id=current.id, user=user)
    assert post_token(new_token).status_code == 200


def test_account_hourly_resend_limit(pending):
    user, verification, _ = pending
    for _ in range(6):
        age_request(verification)
        request_email_verification(email=user.email)
        verification = EmailVerificationToken.objects.get(user=user, invalidated_at__isnull=True)
    assert EmailVerificationToken.objects.filter(user=user).count() == 5


def test_verified_user_is_not_sent_another_email(pending, mailoutbox):
    user, verification, token = pending
    verify_email(token=token)
    age_request(verification)
    request_email_verification(email=user.email)
    assert deliver_pending_verification_emails() == 0
    assert mailoutbox == []
    assert EmailVerificationToken.objects.count() == 1


def test_delivery_failure_is_retryable_without_logging_secrets(pending, mailoutbox, caplog):
    _, verification, token = pending
    with patch("apps.accounts.services.send_verification_message", side_effect=OSError(token)):
        assert deliver_pending_verification_emails() == 0
    verification.refresh_from_db()
    assert verification.sent_at is None
    assert verification.delivery_attempts == 1
    assert verification.next_attempt_at > timezone.now()
    assert token not in caplog.text
    assert deliver_pending_verification_emails() == 0
    verification.next_attempt_at = timezone.now() - timedelta(seconds=1)
    verification.save()
    assert deliver_pending_verification_emails() == 1
    assert len(mailoutbox) == 1


def test_delivery_stops_after_five_failures(pending):
    _, verification, _ = pending
    with patch("apps.accounts.services.send_verification_message", side_effect=OSError()):
        for _ in range(6):
            EmailVerificationToken.objects.filter(pk=verification.id).update(
                next_attempt_at=timezone.now() - timedelta(seconds=1),
            )
            deliver_pending_verification_emails()
    verification.refresh_from_db()
    assert verification.delivery_attempts == 5
    assert verification.sent_at is None


@pytest.mark.parametrize("change", ["email", "disabled", "inactive", "expired"])
def test_stale_delivery_is_suppressed(pending, mailoutbox, change):
    user, verification, _ = pending
    if change == "email":
        user.email = "different@example.com"
    elif change == "disabled":
        user.status = User.Status.DISABLED
    elif change == "inactive":
        user.is_active = False
    else:
        verification.expires_at = timezone.now()
        verification.save()
    user.save()
    assert deliver_pending_verification_emails() == 0
    assert mailoutbox == []


def test_registration_rolls_back_user_outbox_and_audit_together():
    with (
        patch("apps.accounts.services.record_event", side_effect=RuntimeError("audit failure")),
        pytest.raises(RuntimeError),
    ):
        register_user(email="rollback@example.com", password="Cedar-Lantern-581!Fox")
    assert not User.objects.filter(email="rollback@example.com").exists()
    assert EmailVerificationToken.objects.count() == 0
    assert AuditLog.objects.count() == 0


def test_verification_rolls_back_if_audit_fails(pending):
    user, verification, token = pending
    with (
        patch("apps.accounts.services.record_event", side_effect=RuntimeError("audit failure")),
        pytest.raises(RuntimeError),
    ):
        verify_email(token=token)
    user.refresh_from_db()
    verification.refresh_from_db()
    assert user.email_verified_at is None
    assert verification.consumed_at is None


def test_only_one_open_verification_is_allowed(pending):
    user, _, _ = pending
    with pytest.raises(IntegrityError), transaction.atomic():
        EmailVerificationToken.objects.create(
            user=user,
            email=user.email,
            expires_at=timezone.now() + timedelta(minutes=1),
        )


def test_confirmation_page_does_not_consume_token(pending):
    user, verification, _ = pending
    response = APIClient().get(reverse("accounts:verify-email"))
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["Referrer-Policy"] == "no-referrer"
    assert "script-src 'nonce-" in response["Content-Security-Policy"]
    assert b"Verify email" in response.content
    verification.refresh_from_db()
    assert verification.consumed_at is None


def test_throttle_and_cache_outage_use_safe_errors(settings):
    settings.ACCOUNT_THROTTLE_RATES = {"verify_email": (2, 60)}
    for _ in range(2):
        assert post_token("bad").status_code == 400
    limited = post_token("bad")
    assert limited.status_code == 429
    assert int(limited["Retry-After"]) > 0
    cache.clear()
    with patch("api.v1.accounts.throttles.cache.add", side_effect=ConnectionError()):
        response = post_token("bad")
    assert response.status_code == 503
    assert response.data["error"]["code"] == "account_security_unavailable"


def test_registration_and_resend_are_throttled(settings):
    settings.ACCOUNT_THROTTLE_RATES = {"register": (1, 60), "resend_verification": (1, 60)}
    client = APIClient()
    for name in ("register", "resend-verification"):
        assert client.post(reverse(f"accounts:{name}"), {}, format="json").status_code == 400
        assert client.post(reverse(f"accounts:{name}"), {}, format="json").status_code == 429


def test_oversized_or_missing_token_does_not_leak_payload():
    for payload in ({}, {"token": "a" * 257}, {"token": ""}):
        response = APIClient().post(reverse("accounts:verify-email"), payload, format="json")
        assert response.status_code == 400
        assert response.data["error"]["code"] == "validation_error"


def test_tokens_redacted_in_plain_and_url_encoded_text(pending):
    _, _, token = pending
    encoded = token.replace(":", "%3A")
    assert redact_string(token) == REDACTED
    assert redact_string(encoded) == REDACTED
    assert redact_value({"password_confirmation": "sensitive"}) == {
        "password_confirmation": REDACTED,
    }
    assert unquote(token) not in redact_string("verification=" + token)


def test_audit_identifies_verified_user_and_request_without_secrets(pending):
    user, _, token = pending
    response = APIClient().post(
        reverse("accounts:verify-email"),
        {"token": token},
        format="json",
        HTTP_X_REQUEST_ID="verification-test-123",
    )
    assert response.status_code == 200
    audit = AuditLog.objects.get(action="account.email_verified")
    assert audit.actor_id == audit.target_id == user.id
    assert audit.request_id == "verification-test-123"
    assert token not in str(audit.__dict__)
    assert user.email not in str(audit.__dict__)
    with pytest.raises(TypeError):
        audit.save()
    with pytest.raises(TypeError):
        audit.delete()
    with pytest.raises(TypeError):
        AuditLog.objects.filter(pk=audit.pk).update(action="changed")
    with pytest.raises(TypeError):
        AuditLog.objects.all().delete()


@pytest.mark.django_db(transaction=True)
def test_concurrent_verification_only_succeeds_once(pending):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    user, _, token = pending
    barrier = Barrier(2)

    def consume():
        try:
            barrier.wait(timeout=10)
            try:
                verify_email(token=token)
            except InvalidEmailVerificationError:
                return False
            return True
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(results) == [False, True]
    assert AuditLog.objects.filter(action="account.email_verified", target_id=user.id).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_delivery_sends_one_email(pending, mailoutbox):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    _, verification, _ = pending
    barrier = Barrier(2)

    def deliver():
        try:
            barrier.wait(timeout=10)
            return deliver_verification_email(verification_id=verification.id)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: deliver(), range(2)))
    assert sorted(results) == [False, True]
    assert len(mail.outbox) == 1
