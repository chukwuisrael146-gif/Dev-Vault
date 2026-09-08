"""Read-only consistency check; never reset customer counters automatically."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import BigIntegerField, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce

from apps.access.models import QuotaAdjustment, QuotaBucket
from apps.usage.models import QuotaReservation, UsageAggregate, UsageEvent


class Command(BaseCommand):
    help = "Check quota ledgers and aggregate totals in a consistent read-only snapshot."

    @transaction.atomic
    def handle(self, *args, **options):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        reservations = (
            QuotaReservation.objects.filter(bucket_id=OuterRef("pk"))
            .values("bucket_id")
            .annotate(total=Sum("units"))
            .values("total")
        )
        adjustments = (
            QuotaAdjustment.objects.filter(bucket_id=OuterRef("pk"))
            .values("bucket_id")
            .annotate(total=Sum("delta"))
            .values("total")
        )
        mismatches = 0
        for bucket in QuotaBucket.objects.annotate(
            reserved_total=Coalesce(Subquery(reservations), 0, output_field=BigIntegerField()),
            adjustment_total=Coalesce(Subquery(adjustments), 0, output_field=BigIntegerField()),
        ).iterator(chunk_size=1000):
            mismatches += int(
                bucket.used != bucket.reserved_total or bucket.adjustment != bucket.adjustment_total
            )
        events = UsageEvent.objects.filter(aggregation_receipt__isnull=False)
        aggregates = UsageAggregate.objects.aggregate(requests=Sum("requests"), units=Sum("units"))
        aggregate_mismatch = (aggregates["requests"] or 0) != events.count() or (
            aggregates["units"] or 0
        ) != (events.aggregate(total=Sum("units"))["total"] or 0)
        pending = UsageEvent.objects.filter(aggregation_receipt__isnull=True).count()
        self.stdout.write(
            f"Quota ledger mismatches: {mismatches}; aggregate totals mismatch: "
            f"{aggregate_mismatch}; pending aggregation: {pending}. No records changed."
        )
        if mismatches or aggregate_mismatch:
            raise CommandError("Usage reconciliation failed. Investigate before repairing data.")
