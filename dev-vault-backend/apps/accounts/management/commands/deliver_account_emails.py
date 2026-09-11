import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.accounts.profile_services import deliver_pending_password_resets
from apps.accounts.services import deliver_pending_verification_emails


class Command(BaseCommand):
    help = "Deliver a batch of queued verification and password reset emails."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Poll until Ctrl+C (local use).")
        parser.add_argument("--interval", type=int, default=5, help="Polling interval in seconds.")

    def handle(self, *args, **options):
        if not 1 <= options["interval"] <= 60:
            raise CommandError("The polling interval must be between 1 and 60 seconds.")
        if settings.MAILERS["default"]["BACKEND"].endswith("filebased.EmailBackend"):
            self.stdout.write(
                self.style.WARNING(
                    "File mode: emails are saved locally, not sent to inboxes. "
                    "Configure SMTP and DJANGO_EMAIL_MODE=smtp for delivery."
                )
            )
        try:
            while True:
                close_old_connections()
                verified = deliver_pending_verification_emails()
                resets = deliver_pending_password_resets()
                if verified or resets or not options["watch"]:
                    self.stdout.write(
                        f"Email backend accepted {verified} verification "
                        f"and {resets} reset email(s)."
                    )
                if not options["watch"]:
                    return
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Account email worker stopped.")
        finally:
            close_old_connections()
