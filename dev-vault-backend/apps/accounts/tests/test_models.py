import uuid

import pytest

from apps.accounts.models import User


@pytest.mark.django_db
def test_user_uses_normalized_email_and_uuid_primary_key() -> None:
    user = User.objects.create_user(email="  PERSON@Example.COM ", password="not-a-real-password")

    assert user.email == "person@example.com"
    assert isinstance(user.id, uuid.UUID)
    assert user.username is None
