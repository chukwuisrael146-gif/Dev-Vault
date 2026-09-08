"""Transactional infrastructure for retryable commands; never stores response secrets."""

import hashlib
import json
from contextlib import contextmanager
from uuid import UUID

from django.db import transaction
from django.utils.crypto import salted_hmac

from apps.core.exceptions import ConflictError, DomainError
from apps.core.models import IdempotencyRecord


@contextmanager
def creation_command(*, actor_id: UUID, scope: str, key: str, values: dict):
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.isascii():
        raise DomainError(
            code="idempotency_key_required",
            message="Supply an Idempotency-Key header of 1–128 ASCII characters.",
        )
    fingerprint = salted_hmac(
        "devvault.idempotency.v1",
        json.dumps(values, sort_keys=True, separators=(",", ":"), default=str),
        algorithm="sha256",
    ).hexdigest()
    with transaction.atomic():
        row, _ = IdempotencyRecord.objects.get_or_create(
            actor_id=actor_id,
            scope=scope,
            key_hash=hashlib.sha256(key.encode()).hexdigest(),
            defaults={"request_hash": fingerprint},
        )
        row = IdempotencyRecord.objects.select_for_update().get(pk=row.pk)
        if row.request_hash != fingerprint:
            raise ConflictError(
                code="idempotency_conflict",
                message="This Idempotency-Key was used with different input.",
            )
        yield row
        if row.resource_id is None:
            raise RuntimeError("An idempotent creation must record its result before commit.")


def remember_created(row: IdempotencyRecord, resource_id: UUID) -> None:
    row.resource_id = resource_id
    row.save(update_fields=("resource_id", "updated_at"))
