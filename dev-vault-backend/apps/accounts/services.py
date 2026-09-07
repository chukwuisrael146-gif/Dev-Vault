import logging
import secrets
from datetime import timedelta
from smtplib import SMTPException
from uuid import UUID

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.emails import send_verification_message
from apps.accounts.exceptions import EmailAlreadyRegisteredError, InvalidEmailVerificationError
from apps.accounts.managers import UserManager
from apps.accounts.models import EmailVerificationToken, User
from apps.accounts.tokens import validate_verification_signature, verification_id_from_token
from apps.audit.services import record_event

logger = logging.getLogger(__name__)


def register_user(*, email: str, password: str) -> User:
    """Create a new account that must verify its email before authentication."""

    normalized_email = UserManager.normalize_email_address(email)

    if User.objects.filter(email=normalized_email).exists():
        raise EmailAlreadyRegisteredError()

    user = User(
        email=normalized_email,
        status=User.Status.PENDING_VERIFICATION,
        is_active=True,
    )

    validate_password(password, user=user)
    user.set_password(password)

    try:
        with transaction.atomic():
            user.save()
            _issue_email_verification(user=user)
            record_event(action="account.registered", target_id=user.id)
    except IntegrityError as exc:
        if User.objects.filter(email=normalized_email).exists():
            raise EmailAlreadyRegisteredError() from exc
        raise

    return user


def _issue_email_verification(*, user: User) -> None:
    """Caller must lock the user (or have just inserted it) inside a transaction."""
    now = timezone.now()
    EmailVerificationToken.objects.filter(
        user=user,
        consumed_at__isnull=True,
        invalidated_at__isnull=True,
    ).update(invalidated_at=now, updated_at=now)
    EmailVerificationToken.objects.create(
        user=user,
        email=user.email,
        expires_at=now + timedelta(seconds=settings.EMAIL_VERIFICATION_TTL_SECONDS),
    )
    record_event(action="account.email_verification_requested", target_id=user.id)


@transaction.atomic
def request_email_verification(*, email: str) -> None:
    """Always return silently; existence, status and resend suppression stay private."""
    user = (
        User.objects.select_for_update()
        .filter(
            email=UserManager.normalize_email_address(email),
            status=User.Status.PENDING_VERIFICATION,
            is_active=True,
            email_verified_at__isnull=True,
        )
        .first()
    )
    if user is None:
        return
    now = timezone.now()
    recent = EmailVerificationToken.objects.filter(user=user)
    if recent.filter(
        created_at__gt=now - timedelta(seconds=settings.EMAIL_VERIFICATION_RESEND_SECONDS),
    ).exists():
        return
    if recent.filter(created_at__gt=now - timedelta(hours=1)).count() >= 5:
        return
    _issue_email_verification(user=user)


@transaction.atomic
def verify_email(*, token: str) -> User:
    verification_id = verification_id_from_token(token)
    candidate = EmailVerificationToken.objects.filter(pk=verification_id).first()
    if candidate is None:
        raise InvalidEmailVerificationError()
    # All issuance, delivery and consumption lock user then token in the same order.
    user = User.objects.select_for_update().filter(pk=candidate.user_id).first()
    verification = (
        EmailVerificationToken.objects.select_for_update()
        .filter(
            pk=verification_id,
        )
        .first()
    )
    if user is None or verification is None:
        raise InvalidEmailVerificationError()
    validate_verification_signature(token=token, verification_id=verification_id, user=user)
    now = timezone.now()
    if (
        verification.consumed_at is not None
        or verification.invalidated_at is not None
        or verification.expires_at <= now
        or verification.email != user.email
        or not user.is_active
        or user.status != User.Status.PENDING_VERIFICATION
        or user.email_verified_at is not None
    ):
        raise InvalidEmailVerificationError()

    verification.consumed_at = now
    verification.save(update_fields=("consumed_at", "updated_at"))
    user.email_verified_at = now
    user.status = User.Status.ACTIVE
    user.save(update_fields=("email_verified_at", "status", "updated_at"))
    record_event(action="account.email_verified", target_id=user.id, actor_id=user.id)
    return user


@transaction.atomic
def deliver_verification_email(*, verification_id: UUID) -> bool:
    """At-least-once SMTP delivery; repeated attempts cannot reactivate used links."""
    candidate = EmailVerificationToken.objects.filter(pk=verification_id).first()
    if candidate is None:
        return False
    user = User.objects.select_for_update().filter(pk=candidate.user_id).first()
    verification = (
        EmailVerificationToken.objects.select_for_update()
        .filter(
            pk=verification_id,
        )
        .first()
    )
    if user is None or verification is None:
        return False
    now = timezone.now()
    if (
        verification.sent_at is not None
        or verification.consumed_at is not None
        or verification.invalidated_at is not None
        or verification.expires_at <= now
        or verification.next_attempt_at > now
        or verification.delivery_attempts >= 5
    ):
        return False
    if (
        verification.email != user.email
        or not user.is_active
        or user.status != User.Status.PENDING_VERIFICATION
        or user.email_verified_at is not None
    ):
        verification.invalidated_at = now
        verification.save(update_fields=("invalidated_at", "updated_at"))
        return False
    verification.delivery_attempts += 1
    try:
        send_verification_message(verification=verification, user=user)
    except (OSError, SMTPException) as exc:
        delay = min(3600, 30 * 2**verification.delivery_attempts) + secrets.randbelow(30)
        verification.next_attempt_at = now + timedelta(seconds=delay)
        logger.warning(
            "Verification email delivery failed",
            extra={"error_type": type(exc).__name__, "outcome": "delivery_failed"},
        )
    else:
        verification.sent_at = timezone.now()
    verification.save(
        update_fields=("sent_at", "delivery_attempts", "next_attempt_at", "updated_at"),
    )
    return verification.sent_at is not None


def deliver_pending_verification_emails(*, batch_size: int = 25) -> int:
    """Drain committed outbox rows. SMTP/network failures are retried on later runs."""
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")
    now = timezone.now()
    ids = list(
        EmailVerificationToken.objects.filter(
            sent_at__isnull=True,
            consumed_at__isnull=True,
            invalidated_at__isnull=True,
            expires_at__gt=now,
            next_attempt_at__lte=now,
            delivery_attempts__lt=5,
        )
        .order_by("next_attempt_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    return sum(deliver_verification_email(verification_id=pk) for pk in ids)
