from django.core.management.base import BaseCommand

from apps.accounts.services import deliver_pending_verification_emails


class Command(BaseCommand):
    help = "Deliver one batch of pending verification emails using the configured mailer."

    def handle(self, *args, **options):
        sent = deliver_pending_verification_emails()
        self.stdout.write(self.style.SUCCESS(f"Delivered {sent} verification email(s)."))
