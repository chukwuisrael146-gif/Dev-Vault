import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import RefreshTokenSession, User


@pytest.mark.django_db
def test_user_uses_normalized_email_and_uuid_primary_key() -> None:
    user = User.objects.create_user(
        email="  PERSON@Example.COM ",
        password="not-a-real-password",
    )

    assert user.email == "person@example.com"
    assert isinstance(user.id, uuid.UUID)
    assert user.username is None
    assert user.status == User.Status.ACTIVE


@pytest.mark.django_db
def test_disabled_user_cannot_authenticate() -> None:
    user = User.objects.create_user(
        email="person@example.com",
        password="not-a-real-password",
        status=User.Status.DISABLED,
    )

    assert user.can_authenticate is False


@pytest.mark.django_db
def test_refresh_session_is_usable_before_expiry() -> None:
    user = User.objects.create_user(
        email="person@example.com",
        password="not-a-real-password",
    )
    session = RefreshTokenSession.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(days=7),
    )

    assert session.is_usable is True
    assert session.is_expired is False
    assert session.is_revoked is False


@pytest.mark.django_db
def test_revoked_refresh_session_is_not_usable() -> None:
    user = User.objects.create_user(
        email="person@example.com",
        password="not-a-real-password",
    )
    session = RefreshTokenSession.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(days=7),
        revoked_at=timezone.now(),
    )

    assert session.is_usable is False
    assert session.is_revoked is True