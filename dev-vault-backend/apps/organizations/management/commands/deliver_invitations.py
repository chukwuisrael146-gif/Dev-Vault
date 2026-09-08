from django.core.management.base import BaseCommand

from apps.organizations.services import deliver_pending_invitations


class Command(BaseCommand):
    help = "Deliver a batch of queued organization invitations using the configured mailer."

    def handle(self, *args, **options):
        self.stdout.write(f"Delivered {deliver_pending_invitations()} invitation email(s).")
