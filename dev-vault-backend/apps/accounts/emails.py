from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse

from apps.accounts.models import EmailVerificationToken, User
from apps.accounts.tokens import make_verification_token


def send_verification_message(*, verification: EmailVerificationToken, user: User) -> None:
    token = make_verification_token(verification_id=verification.id, user=user)
    # Use a configured origin, never the request Host header. Fragments aren't sent to servers.
    link = (
        settings.ACCOUNT_PUBLIC_BASE_URL.rstrip("/")
        + reverse("accounts:verify-email")
        + "#"
        + urlencode({"token": token})
    )
    message = EmailMessage(
        subject="Verify your DevVault email",
        body=(
            "Welcome to DevVault. Open this link and select Verify email:\n\n"
            f"{link}\n\n"
            f"This link expires at {verification.expires_at.isoformat()} (UTC) "
            "and can only be used once.\n"
            "If you did not request this account, you can ignore this email.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[verification.email],
    )
    if message.send(using="default") != 1:
        raise OSError("Email backend did not accept the message")
