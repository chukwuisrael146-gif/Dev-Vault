"""Private, bounded export artifacts. No public object URLs or bucket-wide operations."""

import tempfile
from pathlib import Path

from django.conf import settings


class ExportStorageError(OSError):
    pass


def export_path(job):
    root = Path(settings.EXPORT_ROOT).resolve()
    candidate = root / f"{job._meta.label_lower}-{job.id}.csv"
    if candidate.parent != root or candidate.is_symlink():
        raise ValueError("Invalid export path")
    return candidate


def object_key(job):
    prefix = settings.EXPORT_S3_PREFIX.strip("/")
    if not prefix or any(part in {"", ".", ".."} for part in prefix.split("/")):
        raise ExportStorageError("Invalid export namespace")
    return f"{prefix}/{job.organization_id}/{job._meta.label_lower}/{job.id}.csv"


def s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3", region_name=settings.EXPORT_S3_REGION,
        config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"}),
    )


def upload_export(job, path):
    import os

    if job.storage_backend == "local":
        os.replace(path, export_path(job))
        return
    if job.storage_backend != "s3":
        raise ExportStorageError("Unsupported export backend")
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        with s3_client() as client, path.open("rb") as stream:
            client.put_object(
                Bucket=settings.EXPORT_S3_BUCKET, Key=object_key(job), Body=stream,
                ContentLength=path.stat().st_size, ContentType="text/csv",
                CacheControl="no-store", ServerSideEncryption="AES256",
            )
    except (BotoCoreError, ClientError) as exc:
        raise ExportStorageError("Export storage unavailable") from exc


def open_export(job):
    if job.storage_backend == "local":
        return export_path(job).open("rb")
    if job.storage_backend != "s3":
        raise ExportStorageError("Unsupported export backend")
    from botocore.exceptions import BotoCoreError, ClientError

    # Buffer before sending HTTP headers: a missing object or failed read produces
    # a safe API error, not a partial CSV with an unexplained 200 response.
    stream = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    try:
        with s3_client() as client:
            response = client.get_object(Bucket=settings.EXPORT_S3_BUCKET, Key=object_key(job))
            body = response["Body"]
            try:
                total = 0
                for chunk in body.iter_chunks(chunk_size=65536):
                    total += len(chunk)
                    if total > settings.EXPORT_MAX_BYTES:
                        raise ExportStorageError("Export exceeded its download limit")
                    stream.write(chunk)
            finally:
                body.close()
        stream.seek(0)
        return stream
    except ClientError as exc:
        stream.close()
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
            raise FileNotFoundError("Export unavailable") from exc
        raise ExportStorageError("Export storage unavailable") from exc
    except (BotoCoreError, OSError):
        stream.close()
        raise ExportStorageError("Export storage unavailable") from None


def delete_export(job):
    if job.storage_backend == "local":
        export_path(job).unlink(missing_ok=True)
        return
    if job.storage_backend != "s3":
        raise ExportStorageError("Unsupported export backend")
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        with s3_client() as client:
            client.delete_object(Bucket=settings.EXPORT_S3_BUCKET, Key=object_key(job))
    except (BotoCoreError, ClientError) as exc:
        raise ExportStorageError("Export storage unavailable") from exc
