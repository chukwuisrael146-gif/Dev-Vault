import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_registration_rejects_passwords_exceeding_login_limit(api_client: APIClient) -> None:
    password = "Long-Password-123!" + "x" * 1024
    response = api_client.post(
        reverse("accounts:register"),
        data={
            "email": "oversized@example.com",
            "password": password,
            "password_confirmation": password,
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert not User.objects.filter(email="oversized@example.com").exists()
    assert password not in str(response.json())


@pytest.mark.django_db
def test_registration_creates_pending_user(api_client: APIClient) -> None:
    response = api_client.post(
        reverse("accounts:register"),
        data={
            "email": "New.User@Example.COM",
            "password": "DevVault-Test-Password-947!",
            "password_confirmation": "DevVault-Test-Password-947!",
        },
        format="json",
    )

    assert response.status_code == 201

    user = User.objects.get(email="new.user@example.com")
    assert user.status == User.Status.PENDING_VERIFICATION
    assert user.email_is_verified is False
    assert user.can_authenticate is False
    assert user.check_password("DevVault-Test-Password-947!")

    response_body = response.json()
    response_user = response_body["data"]["user"]

    assert response_user["id"] == str(user.id)
    assert response_user["email"] == "new.user@example.com"
    assert response_user["status"] == User.Status.PENDING_VERIFICATION
    assert response_user["email_is_verified"] is False
    assert "password" not in response_user
    assert "password_confirmation" not in response_user


@pytest.mark.django_db
def test_registration_rejects_non_matching_passwords(
    api_client: APIClient,
) -> None:
    response = api_client.post(
        reverse("accounts:register"),
        data={
            "email": "person@example.com",
            "password": "DevVault-Test-Password-947!",
            "password_confirmation": "A-Different-Password-583!",
        },
        format="json",
    )

    assert response.status_code == 400
    assert User.objects.filter(email="person@example.com").exists() is False

    response_body = response.json()
    assert response_body["error"]["code"] == "validation_error"
    assert "password_confirmation" in response_body["error"]["details"]


@pytest.mark.django_db
def test_registration_rejects_existing_email(
    api_client: APIClient,
) -> None:
    User.objects.create_user(
        email="existing@example.com",
        password="Existing-Account-Password-832!",
    )

    response = api_client.post(
        reverse("accounts:register"),
        data={
            "email": "EXISTING@EXAMPLE.COM",
            "password": "Another-Strong-Password-471!",
            "password_confirmation": "Another-Strong-Password-471!",
        },
        format="json",
    )

    assert response.status_code == 409

    response_body = response.json()
    assert response_body["error"]["code"] == "email_already_registered"
    assert User.objects.filter(email="existing@example.com").count() == 1


@pytest.mark.django_db
def test_registration_rejects_weak_password(
    api_client: APIClient,
) -> None:
    response = api_client.post(
        reverse("accounts:register"),
        data={
            "email": "person@example.com",
            "password": "password",
            "password_confirmation": "password",
        },
        format="json",
    )

    assert response.status_code == 400
    assert User.objects.filter(email="person@example.com").exists() is False

    response_body = response.json()
    assert response_body["error"]["code"] == "validation_error"
    assert "password" in response_body["error"]["details"]
