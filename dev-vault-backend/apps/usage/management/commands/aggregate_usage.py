from django.core.management.base import BaseCommand

from apps.usage.services import aggregate_pending


class Command(BaseCommand):
    help = "Aggregate a bounded batch of pending usage facts idempotently."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Aggregated {aggregate_pending()} event(s)."))
