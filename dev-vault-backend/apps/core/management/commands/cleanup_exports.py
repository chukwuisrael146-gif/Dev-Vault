from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditExport
from apps.core.export_storage import delete_export
from apps.usage.models import UsageExport


class Command(BaseCommand):
    help = "Dry-run expired CSV cleanup; --apply removes only expired export artifacts."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=1000)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 10000:
            raise CommandError("limit must be between 1 and 10000")
        total = 0
        for model in (UsageExport, AuditExport):
            ids = list(
                model.objects.filter(expires_at__lte=timezone.now())
                .exclude(status="expired")
                .order_by("expires_at")
                .values_list("id", flat=True)[: options["limit"]]
            )
            total += len(ids)
            if not options["apply"]:
                continue
            for identifier in ids:
                with transaction.atomic():
                    job = model.objects.select_for_update().get(pk=identifier)
                    if job.expires_at > timezone.now() or job.status == "expired":
                        continue
                    try:
                        delete_export(job)
                    except (OSError, ValueError) as exc:
                        raise CommandError(
                            "Export cleanup refused an unsafe/unavailable path."
                        ) from exc
                    job.status = "expired"
                    job.save(update_fields=("status", "updated_at"))
        mode = "Removed expired CSV artifacts for" if options["apply"] else "Would expire"
        self.stdout.write(f"{mode} {total} jobs. Source audit and usage facts were preserved.")
