"""Bounded local export storage. Domain modules supply authorized rows and headers."""

import csv
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone


def export_path(job):
    root = Path(settings.EXPORT_ROOT).resolve()
    candidate = root / f"{job._meta.label_lower}-{job.id}.csv"
    if candidate.parent != root or candidate.is_symlink():
        raise ValueError("Invalid export path")
    return candidate


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
    path = export_path(job)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=path.parent,
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
            else:
                job.status, job.row_count = "ready", count
        if job.status == "ready":
            os.replace(temporary, path)
            temporary = None
        job.save(update_fields=("status", "row_count", "failure_code", "updated_at"))
    except OSError:
        job.status, job.failure_code = "failed", "export_storage_unavailable"
        job.save(update_fields=("status", "failure_code", "updated_at"))
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return job.status == "ready"
