from django.core.management.base import BaseCommand

from apps.accounts.profile_services import deliver_pending_password_resets
from apps.accounts.services import deliver_pending_verification_emails


class Command(BaseCommand):
    help = "Deliver a batch of queued verification and password reset emails."

    def handle(self, *args, **options):
        verified = deliver_pending_verification_emails()
        resets = deliver_pending_password_resets()
        self.stdout.write(
            self.style.SUCCESS(f"Delivered {verified} verification and {resets} reset email(s).")
        )
