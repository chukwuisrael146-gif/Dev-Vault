from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction

from apps.accounts.exceptions import EmailAlreadyRegisteredError
from apps.accounts.managers import UserManager
from apps.accounts.models import User


def register_user(*, email: str, password: str) -> User:
    """ Create a new account that must verify its email before authentication."""

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
    except IntegrityError as exc:
        if User.objects.filter(email=normalized_email).exists():
            raise EmailAlreadyRegisteredError() from exc
        raise
    
    return user