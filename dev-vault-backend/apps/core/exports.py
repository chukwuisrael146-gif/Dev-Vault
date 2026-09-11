"""Bounded export creation. Domain modules supply authorized rows and headers."""

import csv
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.export_storage import export_path, upload_export  # noqa: F401


def csv_cell(value):
    text = "" if value is None else str(value)
    # Prevent spreadsheet formula injection, including leading control/space tricks.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


@transaction.atomic
def process_export(model, job_id, headers, rows_for):
    job = model.objects.select_for_update().filter(pk=job_id).first()
    if job is None or job.status != "queued" or job.expires_at <= timezone.now():
        return False
    directory = Path(settings.EXPORT_ROOT).resolve()
    temporary = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=directory,
            prefix=f"{job.id}-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream)
            writer.writerow(headers)
            count = 0
            for count, row in enumerate(rows_for(job), start=1):
                if count > settings.EXPORT_MAX_ROWS:
                    job.status, job.failure_code = "failed", "export_row_limit"
                    break
                writer.writerow([csv_cell(value) for value in row])
                if stream.tell() > settings.EXPORT_MAX_BYTES:
                    job.status, job.failure_code = "failed", "export_byte_limit"
                    break
            else:
                job.status, job.row_count = "ready", count
        if job.status == "ready":
            upload_export(job, temporary)
        job.save(update_fields=("status", "row_count", "failure_code", "updated_at"))
    except (OSError, ValueError):
        job.status, job.failure_code = "failed", "export_storage_unavailable"
        job.save(update_fields=("status", "failure_code", "updated_at"))
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return job.status == "ready"
