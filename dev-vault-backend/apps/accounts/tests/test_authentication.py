from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from django.conf import settings as django_settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, connections
from django.urls import include, path, reverse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from apps.accounts.auth_services import (
    authenticate_access_token,
    login_user,
    logout_session,
    refresh_session,
)
from apps.accounts.exceptions import InvalidLoginError, InvalidSessionTokenError
from apps.accounts.jwt import decode_session_token
from apps.accounts.models import RefreshTokenSession, User
from apps.audit.models import AuditLog
from apps.core.logging import REDACTED, redact_string, redact_value

pytestmark = pytest.mark.django_db
PASSWORD = "Maple-Ocean-392!Frost"


class ProtectedProbe(APIView):
    """Test-only route, exercising the configured default authentication and permission."""

    def get(self, request):
        return Response({"user_id": str(request.user.id), "session_id": str(request.auth.id)})


urlpatterns = [
    path("api/", include("api.urls")),
    path("protected-probe/", ProtectedProbe.as_view()),
]


@pytest.fixture
def active_user():
    return User.objects.create_user(
        email="member@example.com",
        password=PASSWORD,
        status=User.Status.ACTIVE,
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def pair(active_user):
    return login_user(email=active_user.email, password=PASSWORD)[1]


def post(name, data):
    return APIClient().post(reverse(f"accounts:{name}"), data, format="json")


def payload(token):
    return jwt.decode(
        token,
        django_settings.ACCOUNT_JWT_SIGNING_KEY,
        algorithms=["HS256"],
        audience=django_settings.ACCOUNT_JWT_AUDIENCE,
        issuer=django_settings.ACCOUNT_JWT_ISSUER,
    )


def encode(claims, algorithm="HS256", key=None):
    return jwt.encode(claims, key or django_settings.ACCOUNT_JWT_SIGNING_KEY, algorithm=algorithm)


def test_login_returns_safe_tokens_and_session(active_user):
    response = APIClient().post(
        reverse("accounts:login"),
        {"email": "MEMBER@EXAMPLE.COM", "password": PASSWORD, "is_staff": True},
        format="json",
        REMOTE_ADDR="127.0.0.2",
        HTTP_USER_AGENT="DevVault test client",
        HTTP_X_REQUEST_ID="login-test-1",
    )
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["Pragma"] == "no-cache"
    assert not response.cookies
    data = response.data["data"]
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 300
    assert 604798 <= data["refresh_expires_in"] <= 604800
    assert data["user"]["id"] == str(active_user.id)
    assert "password" not in data["user"]
    assert "credential_hash" not in str(data)
    access = payload(data["access_token"])
    refresh = payload(data["refresh_token"])
    session = RefreshTokenSession.objects.get(user=active_user)
    assert session.credential_hash
    assert str(session.id) == access["sid"] == refresh["sid"]
    assert str(session.token_jti) == refresh["jti"]
    assert access["token_type"] == "access"
    assert refresh["token_type"] == "refresh"
    assert session.created_ip_address == "127.0.0.2"
    assert session.user_agent == "DevVault test client"
    assert active_user.email not in str(access)
    assert data["access_token"] not in str(session.__dict__)
    assert data["refresh_token"] not in str(session.__dict__)
    active_user.refresh_from_db()
    assert active_user.last_login is not None
    assert active_user.is_staff is False
    event = AuditLog.objects.get(action="account.login_succeeded")
    assert event.request_id == "login-test-1"
    assert event.actor_id == event.target_id == active_user.id


@pytest.mark.parametrize(
    "state", ["unknown", "bad_password", "pending", "disabled", "inactive", "unverified"]
)
def test_login_denies_all_ineligible_accounts_with_same_error(active_user, state):
    email, password = active_user.email, PASSWORD
    if state == "unknown":
        email = "unknown@example.com"
    elif state == "bad_password":
        password = "Incorrect-Password"
    elif state == "pending":
        active_user.status = User.Status.PENDING_VERIFICATION
    elif state == "disabled":
        active_user.status = User.Status.DISABLED
    elif state == "inactive":
        active_user.is_active = False
    else:
        active_user.email_verified_at = None
    active_user.save()
    response = post("login", {"email": email, "password": password})
    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Bearer")
    assert response.data["error"]["code"] == "invalid_credentials"
    assert response.data["error"]["message"] == "Email or password is incorrect."
    assert RefreshTokenSession.objects.count() == 0
    event = AuditLog.objects.get(action="account.login_failed")
    assert event.outcome == "failure"
    assert event.actor_id is None
    assert event.target_id == (None if state == "unknown" else active_user.id)
    assert email not in str(event.__dict__)


def test_password_change_during_login_cannot_issue_stale_session(active_user):
    def changed_password(raw, encoded):
        result = check_password(raw, encoded)
        User.objects.filter(pk=active_user.pk).update(password=make_password("Replacement-718!"))
        return result

    with (
        patch("apps.accounts.auth_services.check_password", side_effect=changed_password),
        pytest.raises(InvalidLoginError),
    ):
        login_user(email=active_user.email, password=PASSWORD)
    assert RefreshTokenSession.objects.count() == 0
    active_user.refresh_from_db()
    assert active_user.check_password("Replacement-718!")


def test_refresh_rotates_and_preserves_absolute_session_expiry(active_user, pair):
    before = RefreshTokenSession.objects.get(user=active_user)
    response = post("refresh", {"refresh_token": pair.refresh_token})
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    data = response.data["data"]
    assert data["refresh_token"] != pair.refresh_token
    after = RefreshTokenSession.objects.get(pk=before.id)
    assert after.token_jti != before.token_jti
    assert after.expires_at == before.expires_at
    assert payload(data["refresh_token"])["exp"] == payload(pair.refresh_token)["exp"]
    assert authenticate_access_token(access_token=data["access_token"])[0].id == active_user.id
    # Old access tokens remain valid after an ordinary refresh until expiry or revocation.
    assert authenticate_access_token(access_token=pair.access_token)[0].id == active_user.id


def test_refresh_reuse_commits_session_revocation(active_user, pair):
    replacement = refresh_session(refresh_token=pair.refresh_token)
    response = post("refresh", {"refresh_token": pair.refresh_token})
    assert response.status_code == 401
    assert RefreshTokenSession.objects.get(user=active_user).revoked_at is not None
    with pytest.raises(InvalidSessionTokenError):
        refresh_session(refresh_token=replacement.refresh_token)
    for access in (pair.access_token, replacement.access_token):
        with pytest.raises(InvalidSessionTokenError):
            authenticate_access_token(access_token=access)
    assert AuditLog.objects.filter(action="account.refresh_reuse_detected").count() == 1


def test_logout_is_idempotent_and_only_revokes_its_session(active_user, pair):
    second = login_user(email=active_user.email, password=PASSWORD)[1]
    for _ in range(2):
        response = post("logout", {"refresh_token": pair.refresh_token})
        assert response.status_code == 204
        assert not response.content
    assert post("refresh", {"refresh_token": pair.refresh_token}).status_code == 401
    with pytest.raises(InvalidSessionTokenError):
        authenticate_access_token(access_token=pair.access_token)
    assert authenticate_access_token(access_token=second.access_token)[0].id == active_user.id
    assert AuditLog.objects.filter(action="account.logged_out").count() == 1


def test_rotated_refresh_can_still_log_out_its_session(pair):
    replacement = refresh_session(refresh_token=pair.refresh_token)
    logout_session(refresh_token=pair.refresh_token)
    with pytest.raises(InvalidSessionTokenError):
        authenticate_access_token(access_token=replacement.access_token)


@pytest.mark.parametrize("operation", ["refresh", "logout"])
def test_access_tokens_cannot_be_used_as_refresh_tokens(pair, operation):
    response = post(operation, {"refresh_token": pair.access_token})
    assert response.status_code == 401
    assert RefreshTokenSession.objects.get().revoked_at is None


@pytest.mark.parametrize(
    "change", ["disabled", "inactive", "email", "password", "unverified", "expired"]
)
def test_account_and_session_changes_invalidate_access_and_refresh(active_user, pair, change):
    if change == "disabled":
        active_user.status = User.Status.DISABLED
    elif change == "inactive":
        active_user.is_active = False
    elif change == "email":
        active_user.email = "changed@example.com"
    elif change == "password":
        active_user.set_password("Changed-Cedar-372!")
    elif change == "unverified":
        active_user.email_verified_at = None
    else:
        RefreshTokenSession.objects.filter(user=active_user).update(expires_at=timezone.now())
    active_user.save()
    with pytest.raises(InvalidSessionTokenError):
        authenticate_access_token(access_token=pair.access_token)
    assert post("refresh", {"refresh_token": pair.refresh_token}).status_code == 401
    assert RefreshTokenSession.objects.get().revoked_at is not None


def test_existing_blank_credential_hash_fails_closed(pair):
    RefreshTokenSession.objects.update(credential_hash="")
    with pytest.raises(InvalidSessionTokenError):
        authenticate_access_token(access_token=pair.access_token)


@pytest.mark.parametrize(
    "change",
    [
        "signature",
        "audience",
        "issuer",
        "expired",
        "future",
        "missing_sub",
        "bad_sub",
        "missing_sid",
        "bad_sid",
        "bad_jti",
        "wrong_kind",
        "missing_kind",
        "bool_exp",
        "long_lifetime",
    ],
)
def test_invalid_refresh_claims_rejected_without_revoking_valid_session(pair, change):
    claims = payload(pair.refresh_token)
    if change == "signature":
        token = encode(claims, key="wrong-key-that-is-at-least-thirty-two-bytes")
    else:
        if change == "audience":
            claims["aud"] = "another-service"
        elif change == "issuer":
            claims["iss"] = "another-issuer"
        elif change == "expired":
            claims["exp"] = int(timezone.now().timestamp()) - 1
        elif change == "future":
            claims["iat"] += 60
            claims["nbf"] += 60
        elif change.startswith("missing_"):
            del claims[{"missing_kind": "token_type"}.get(change, change.removeprefix("missing_"))]
        elif change in {"bad_sub", "bad_sid", "bad_jti"}:
            claims[change.removeprefix("bad_")] = "not-a-uuid"
        elif change == "wrong_kind":
            claims["token_type"] = "access"
        elif change == "bool_exp":
            claims["exp"] = True
        else:
            claims["exp"] = claims["iat"] + 99999999
        token = encode(claims)
    response = post("refresh", {"refresh_token": token})
    assert response.status_code == 401
    assert response.data["error"]["code"] == "invalid_token"
    assert token not in str(response.data)
    assert RefreshTokenSession.objects.get().revoked_at is None


@pytest.mark.parametrize("algorithm", ["HS384", "none"])
def test_algorithm_substitution_rejected(pair, algorithm):
    claims = payload(pair.refresh_token)
    key = None if algorithm == "none" else django_settings.ACCOUNT_JWT_SIGNING_KEY
    token = jwt.encode(claims, key, algorithm=algorithm)
    assert post("refresh", {"refresh_token": token}).status_code == 401


def test_wrong_user_cannot_refresh_or_logout_another_session(pair):
    claims = payload(pair.refresh_token)
    claims["sub"] = str(uuid4())
    token = encode(claims)
    assert post("refresh", {"refresh_token": token}).status_code == 401
    assert post("logout", {"refresh_token": token}).status_code == 401
    assert RefreshTokenSession.objects.get().revoked_at is None


def test_expired_access_and_refresh_tokens_are_rejected(pair):
    for token, kind in ((pair.access_token, "access"), (pair.refresh_token, "refresh")):
        claims = payload(token)
        claims["iat"] -= 900000
        claims["nbf"] -= 900000
        claims["exp"] -= 900000
        with pytest.raises(InvalidSessionTokenError):
            decode_session_token(token=encode(claims), kind=kind)


def test_default_authentication_accepts_only_current_bearer_access(settings, active_user, pair):
    settings.ROOT_URLCONF = __name__
    client = APIClient()
    assert client.get("/protected-probe/").status_code == 401
    for header in (
        "Basic abc",
        "Bearer",
        "Bearer bad extra",
        "Bearer dv_live_key_secret",
        "Bearer " + pair.refresh_token,
    ):
        response = client.get("/protected-probe/", HTTP_AUTHORIZATION=header)
        assert response.status_code == 401
        assert response.data["error"]["code"] == "invalid_token"
    response = client.get("/protected-probe/", HTTP_AUTHORIZATION="Bearer " + pair.access_token)
    assert response.status_code == 200
    assert response.data["user_id"] == str(active_user.id)
    logout_session(refresh_token=pair.refresh_token)
    assert (
        client.get(
            "/protected-probe/", HTTP_AUTHORIZATION="Bearer " + pair.access_token
        ).status_code
        == 401
    )


def test_cookie_login_is_not_dashboard_api_authentication(settings, active_user):
    settings.ROOT_URLCONF = __name__
    client = APIClient()
    client.force_login(active_user)
    assert client.get("/protected-probe/").status_code == 401


def test_login_payload_limits_and_session_metadata(active_user):
    assert post("login", {"email": active_user.email, "password": "x" * 1025}).status_code == 400
    assert post("refresh", {"refresh_token": "x" * 4097}).status_code == 400
    assert post("logout", {}).status_code == 400
    login_user(
        email=active_user.email, password=PASSWORD, source_ip="invalid", user_agent="x" * 900
    )
    session = RefreshTokenSession.objects.get()
    assert session.created_ip_address is None
    assert len(session.user_agent) == 512


def test_throttled_login_does_not_check_password(active_user, settings):
    settings.ACCOUNT_THROTTLE_RATES = {"login": (1, 300)}
    assert post("login", {"email": active_user.email, "password": "wrong"}).status_code == 401
    with patch("apps.accounts.auth_services.check_password") as check:
        response = post("login", {"email": active_user.email, "password": PASSWORD})
    assert response.status_code == 429
    check.assert_not_called()


def test_login_and_session_changes_roll_back_on_audit_failure(active_user, pair):
    before = RefreshTokenSession.objects.get()
    for operation in (
        lambda: login_user(email=active_user.email, password=PASSWORD),
        lambda: refresh_session(refresh_token=pair.refresh_token),
        lambda: logout_session(refresh_token=pair.refresh_token),
    ):
        with (
            patch(
                "apps.accounts.auth_services.record_event", side_effect=RuntimeError("audit failed")
            ),
            pytest.raises(RuntimeError),
        ):
            operation()
    assert RefreshTokenSession.objects.count() == 1
    after = RefreshTokenSession.objects.get()
    assert after.token_jti == before.token_jti
    assert after.revoked_at is None


def test_tokens_are_not_in_audits_logs_or_object_repr(pair):
    assert pair.access_token not in repr(pair)
    assert pair.refresh_token not in repr(pair)
    assert redact_string(pair.access_token) == REDACTED
    assert redact_string(pair.refresh_token) == REDACTED
    assert redact_value({"access_token": pair.access_token}) == {"access_token": REDACTED}
    assert pair.access_token not in str(list(AuditLog.objects.values()))
    assert pair.refresh_token not in str(list(AuditLog.objects.values()))


@pytest.mark.django_db(transaction=True)
def test_concurrent_refresh_detects_reuse_and_revokes_family(pair):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    barrier = Barrier(2)

    def rotate():
        try:
            barrier.wait(timeout=10)
            try:
                return refresh_session(refresh_token=pair.refresh_token)
            except InvalidSessionTokenError:
                return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert RefreshTokenSession.objects.get().revoked_at is not None
    assert AuditLog.objects.filter(action="account.refresh_reuse_detected").count() == 1
    for result in results:
        if result:
            with pytest.raises(InvalidSessionTokenError):
                authenticate_access_token(access_token=result.access_token)


@pytest.mark.django_db(transaction=True)
def test_concurrent_logout_and_refresh_cannot_leave_active_session(pair):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    barrier = Barrier(2)

    def command(refresh):
        try:
            barrier.wait(timeout=10)
            try:
                if refresh:
                    return refresh_session(refresh_token=pair.refresh_token)
                logout_session(refresh_token=pair.refresh_token)
            except InvalidSessionTokenError:
                return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(command, (True, False)))
    assert RefreshTokenSession.objects.get().revoked_at is not None
    assert AuditLog.objects.filter(action="account.logged_out").count() == 1
    for result in results:
        if result:
            with pytest.raises(InvalidSessionTokenError):
                authenticate_access_token(access_token=result.access_token)
