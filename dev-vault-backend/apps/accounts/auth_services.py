"""Dashboard login and session lifecycle use cases, independent of HTTP."""

from datetime import timedelta
from ipaddress import ip_address
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.accounts.exceptions import InvalidLoginError, InvalidSessionTokenError
from apps.accounts.jwt import TokenPair, credential_hash, decode_session_token, issue_token_pair
from apps.accounts.managers import UserManager
from apps.accounts.models import RefreshTokenSession, User
from apps.audit.services import record_event


def _eligible(user: User) -> bool:
    return user.can_authenticate and user.email_is_verified


def _session_is_current(session: RefreshTokenSession, user: User) -> bool:
    return (
        session.is_usable
        and _eligible(user)
        and constant_time_compare(session.credential_hash, credential_hash(user))
    )


def login_user(
    *,
    email: str,
    password: str,
    source_ip: str | None = None,
    user_agent: str = "",
) -> tuple[User, TokenPair]:
    candidate = User.objects.filter(email=UserManager.normalize_email_address(email)).first()
    # No hash-upgrade writes outside our transaction; a password change must not be overwritten.
    password_valid = False
    if candidate is None:
        make_password(password)  # Approximate the password-check cost for an unknown email.
    else:
        password_valid = check_password(password, candidate.password)
    if not password_valid or candidate is None:
        record_event(
            action="account.login_failed",
            target_id=candidate.id if candidate else None,
            outcome="failure",
        )
        raise InvalidLoginError()
    try:
        source_ip = str(ip_address(source_ip)) if source_ip else None
    except ValueError:
        source_ip = None

    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=candidate.pk).first()
        if (
            user is None
            or not _eligible(user)
            or not constant_time_compare(user.password, candidate.password)
        ):
            record_event(action="account.login_failed", target_id=candidate.pk, outcome="failure")
        else:
            now = timezone.now()
            session = RefreshTokenSession.objects.create(
                user=user,
                expires_at=now + timedelta(seconds=settings.ACCOUNT_REFRESH_TOKEN_SECONDS),
                credential_hash=credential_hash(user),
                created_ip_address=source_ip,
                user_agent=user_agent[:512],
                last_used_at=now,
            )
            pair = issue_token_pair(session=session, now=now)
            user.last_login = now
            user.save(update_fields=("last_login", "updated_at"))
            record_event(action="account.login_succeeded", target_id=user.id, actor_id=user.id)
            return user, pair
    # Leave the transaction normally so a failed-login audit event is not rolled back.
    raise InvalidLoginError()


def refresh_session(*, refresh_token: str) -> TokenPair:
    claims = decode_session_token(token=refresh_token, kind="refresh")
    pair = None
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=claims.user_id).first()
        session = (
            RefreshTokenSession.objects.select_for_update()
            .filter(
                pk=claims.session_id,
                user_id=claims.user_id,
            )
            .first()
        )
        if user is not None and session is not None and session.revoked_at is None:
            if not _session_is_current(session, user):
                session.revoked_at = timezone.now()
                session.save(update_fields=("revoked_at", "updated_at"))
                record_event(action="account.session_invalidated", target_id=user.id)
            elif session.token_jti != claims.token_id:
                # Reuse of a signed, rotated refresh token invalidates the entire family.
                session.revoked_at = timezone.now()
                session.save(update_fields=("revoked_at", "updated_at"))
                record_event(
                    action="account.refresh_reuse_detected",
                    target_id=user.id,
                    outcome="failure",
                )
            else:
                session.token_jti = uuid4()
                session.last_used_at = timezone.now()
                session.save(update_fields=("token_jti", "last_used_at", "updated_at"))
                pair = issue_token_pair(session=session)
                record_event(action="account.token_refreshed", target_id=user.id, actor_id=user.id)
    # Raising inside atomic() would undo the security-critical reuse revocation.
    if pair is None:
        raise InvalidSessionTokenError()
    return pair


def logout_session(*, refresh_token: str) -> None:
    claims = decode_session_token(token=refresh_token, kind="refresh")
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=claims.user_id).first()
        session = (
            RefreshTokenSession.objects.select_for_update()
            .filter(
                pk=claims.session_id,
                user_id=claims.user_id,
            )
            .first()
        )
        if user is None or session is None:
            raise InvalidSessionTokenError()
        # A valid rotated token may still terminate its own session; never anyone else's.
        if session.revoked_at is None:
            session.revoked_at = timezone.now()
            session.save(update_fields=("revoked_at", "updated_at"))
            record_event(action="account.logged_out", target_id=user.id, actor_id=user.id)


def authenticate_access_token(*, access_token: str) -> tuple[User, RefreshTokenSession]:
    claims = decode_session_token(token=access_token, kind="access")
    session = (
        RefreshTokenSession.objects.select_related("user")
        .filter(
            pk=claims.session_id,
            user_id=claims.user_id,
        )
        .first()
    )
    if session is None or not _session_is_current(session, session.user):
        raise InvalidSessionTokenError()
    return session.user, session
