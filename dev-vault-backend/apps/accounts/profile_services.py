"""Account profile and password lifecycle; no HTTP or Celery dependencies."""

import logging
import secrets
from datetime import timedelta
from smtplib import SMTPException
from urllib.parse import urlencode
from uuid import UUID

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.accounts.exceptions import InvalidLoginError, InvalidSessionTokenError
from apps.accounts.jwt import credential_hash
from apps.accounts.managers import UserManager
from apps.accounts.models import PasswordResetRequest, RefreshTokenSession, User
from apps.audit.services import record_event
from apps.core.exceptions import DomainError

logger = logging.getLogger(__name__)
RESET_PREFIX = "dv_reset_"


class InvalidPasswordReset(DomainError):
    code = "invalid_password_reset"
    message = "This password reset link is invalid or expired. Request a new link."


def _validate_password(user: User, password: str) -> None:
    if not isinstance(password, str) or not 1 <= len(password) <= 1024:
        raise DomainError(
            code="validation_error", message="Password length must be 1–1024 characters."
        )
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        raise DomainError(
            code="validation_error",
            message="The password does not meet the security requirements.",
            details={"new_password": list(exc.messages)},
        ) from exc
    if check_password(password, user.password):
        raise DomainError(code="validation_error", message="Choose a different password.")


def _current_user(actor: User) -> User:
    user = User.objects.select_for_update().filter(pk=actor.pk).first()
    if (
        user is None
        or not user.can_authenticate
        or not user.email_is_verified
        or not constant_time_compare(credential_hash(actor), credential_hash(user))
    ):
        raise InvalidSessionTokenError()
    return user


@transaction.atomic
def update_profile(
    *, actor: User, first_name: str | None = None, last_name: str | None = None
) -> User:
    user = _current_user(actor)
    first_name = user.first_name if first_name is None else first_name
    last_name = user.last_name if last_name is None else last_name
    if len(first_name) > 150 or len(last_name) > 150:
        raise DomainError(code="validation_error", message="Names must be at most 150 characters.")
    user.first_name, user.last_name = first_name.strip(), last_name.strip()
    user.save(update_fields=("first_name", "last_name", "updated_at"))
    record_event(action="account.profile_updated", target_id=user.id, actor_id=user.id)
    return user


def _replace_password(user: User, password: str, *, action: str) -> None:
    _validate_password(user, password)
    user.set_password(password)
    user.save(update_fields=("password", "updated_at"))
    now = timezone.now()
    RefreshTokenSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=now,
        updated_at=now,
    )
    PasswordResetRequest.objects.filter(
        user=user,
        consumed_at__isnull=True,
        invalidated_at__isnull=True,
    ).update(invalidated_at=now, updated_at=now)
    record_event(action=action, target_id=user.id, actor_id=user.id)


@transaction.atomic
def change_password(*, actor: User, current_password: str, new_password: str) -> None:
    user = _current_user(actor)
    if not check_password(current_password, user.password):
        raise InvalidLoginError()
    _replace_password(user, new_password, action="account.password_changed")


def require_recent_login(*, actor: User, session: RefreshTokenSession) -> None:
    """Sensitive actions require a login within 15 minutes; refresh does not renew it."""
    if (
        session is None
        or session.user_id != actor.id
        or not session.is_usable
        or session.created_at < timezone.now() - timedelta(seconds=900)
        or not constant_time_compare(session.credential_hash, credential_hash(actor))
    ):
        raise DomainError(
            code="recent_authentication_required", message="Sign in again to continue."
        )


@transaction.atomic
def request_password_reset(*, email: str) -> None:
    user = (
        User.objects.select_for_update()
        .filter(
            email=UserManager.normalize_email_address(email),
            status=User.Status.ACTIVE,
            is_active=True,
            email_verified_at__isnull=False,
        )
        .first()
    )
    if user is None:
        return
    now = timezone.now()
    recent = PasswordResetRequest.objects.filter(user=user)
    if recent.filter(created_at__gt=now - timedelta(seconds=60)).exists():
        return
    if recent.filter(created_at__gt=now - timedelta(hours=1)).count() >= 5:
        return
    recent.filter(consumed_at__isnull=True, invalidated_at__isnull=True).update(
        invalidated_at=now,
        updated_at=now,
    )
    PasswordResetRequest.objects.create(
        user=user,
        expires_at=now + timedelta(seconds=settings.PASSWORD_RESET_TTL_SECONDS),
        credential_hash=credential_hash(user),
    )
    record_event(action="account.password_reset_requested", target_id=user.id)


def _reset_signer(row: PasswordResetRequest) -> signing.Signer:
    return signing.Signer(salt=f"devvault.password-reset.v1:{row.credential_hash}")


def password_reset_token(row: PasswordResetRequest) -> str:
    return RESET_PREFIX + _reset_signer(row).sign(str(row.id))


@transaction.atomic
def reset_password(*, token: str, new_password: str) -> None:
    try:
        if not token.startswith(RESET_PREFIX) or len(token) > 256:
            raise ValueError
        identifier = UUID(token.removeprefix(RESET_PREFIX).split(":", 1)[0])
    except (AttributeError, ValueError) as exc:
        raise InvalidPasswordReset() from exc
    candidate = PasswordResetRequest.objects.filter(pk=identifier).first()
    if candidate is None:
        raise InvalidPasswordReset()
    user = User.objects.select_for_update().filter(pk=candidate.user_id).first()
    row = PasswordResetRequest.objects.select_for_update().get(pk=identifier)
    if (
        user is None
        or not user.can_authenticate
        or not user.email_is_verified
        or row.consumed_at is not None
        or row.invalidated_at is not None
        or row.expires_at <= timezone.now()
        or not constant_time_compare(row.credential_hash, credential_hash(user))
    ):
        raise InvalidPasswordReset()
    try:
        if _reset_signer(row).unsign(token.removeprefix(RESET_PREFIX)) != str(row.id):
            raise signing.BadSignature
    except signing.BadSignature as exc:
        raise InvalidPasswordReset() from exc
    row.consumed_at = timezone.now()
    row.save(update_fields=("consumed_at", "updated_at"))
    _replace_password(user, new_password, action="account.password_reset_completed")


@transaction.atomic
def deliver_password_reset(*, identifier: UUID) -> bool:
    candidate = PasswordResetRequest.objects.filter(pk=identifier).first()
    if candidate is None:
        return False
    user = User.objects.select_for_update().get(pk=candidate.user_id)
    row = PasswordResetRequest.objects.select_for_update().get(pk=identifier)
    now = timezone.now()
    if (
        row.sent_at is not None
        or row.consumed_at is not None
        or row.invalidated_at is not None
        or row.expires_at <= now
        or row.next_attempt_at > now
        or row.delivery_attempts >= 5
    ):
        return False
    if (
        not user.can_authenticate
        or not user.email_is_verified
        or not constant_time_compare(row.credential_hash, credential_hash(user))
    ):
        row.invalidated_at = now
        row.save(update_fields=("invalidated_at", "updated_at"))
        return False
    link = (
        settings.ACCOUNT_PUBLIC_BASE_URL.rstrip("/")
        + reverse("accounts:password-reset-confirm")
        + "#"
        + urlencode({"token": password_reset_token(row)})
    )
    row.delivery_attempts += 1
    try:
        accepted = EmailMessage(
            subject="Reset your DevVault password",
            body=f"Open this link to choose a new password:\n\n{link}\n\n"
            f"Expires at {row.expires_at.isoformat()} (UTC).\n"
            "If you did not request this, ignore it.\n",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        ).send(using="default")
        if accepted != 1:
            raise OSError("Email was not accepted")
    except (OSError, SMTPException) as exc:
        row.next_attempt_at = now + timedelta(
            seconds=30 * 2**row.delivery_attempts + secrets.randbelow(30)
        )
        logger.warning(
            "Password reset email delivery failed", extra={"error_type": type(exc).__name__}
        )
    else:
        row.sent_at = timezone.now()
    row.save(update_fields=("sent_at", "delivery_attempts", "next_attempt_at", "updated_at"))
    return row.sent_at is not None


def deliver_pending_password_resets() -> int:
    now = timezone.now()
    ids = list(
        PasswordResetRequest.objects.filter(
            sent_at__isnull=True,
            consumed_at__isnull=True,
            invalidated_at__isnull=True,
            expires_at__gt=now,
            next_attempt_at__lte=now,
            delivery_attempts__lt=5,
        )
        .order_by("next_attempt_at", "id")
        .values_list("id", flat=True)[:25]
    )
    return sum(deliver_password_reset(identifier=identifier) for identifier in ids)
