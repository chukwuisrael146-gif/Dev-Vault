"""Validate the configured SMTP connection without sending mail or printing secrets."""

from contextlib import suppress
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import mailers
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Check SMTP connectivity/authentication without sending any email."

    def handle(self, *args, **options):
        if settings.MAILERS["default"]["BACKEND"] != "django.core.mail.backends.smtp.EmailBackend":
            raise CommandError("SMTP is not enabled. Set DJANGO_EMAIL_MODE=smtp in development.")
        connection = mailers.create_connection("default")
        try:
            connection.open()
        except (OSError, SMTPException) as exc:
            # SMTP error strings can contain account details. Only expose the class.
            raise CommandError(
                f"SMTP connection failed ({type(exc).__name__}). "
                "Check the private sender credentials, TLS settings and network."
            ) from None
        finally:
            with suppress(OSError, SMTPException):
                connection.close()
        self.stdout.write(
            self.style.SUCCESS(
                "SMTP connection accepted. No email was sent; inbox delivery is not yet verified."
            )
        )
