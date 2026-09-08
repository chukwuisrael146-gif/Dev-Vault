import http.client
import json
import secrets
import time
from datetime import timedelta

from cryptography.fernet import InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.profile_services import require_recent_login
from apps.audit.services import record_event
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.idempotency import creation_command, remember_created
from apps.organizations.selectors import active_organization, get_organization
from apps.webhooks.crypto import cipher, signature
from apps.webhooks.models import DeliveryAttempt, WebhookDelivery, WebhookEndpoint
from apps.webhooks.transport import UnsafeDestination, destination, post_json

EVENT_TYPES = frozenset(
    {
        "key.created",
        "key.rotated",
        "key.revoked",
        "policy.created",
        "policy.updated",
        "quota.adjusted",
        "quota.threshold_reached",
        "organization.archived",
        "access.rate_limited",
        "access.quota_exceeded",
    }
)


def endpoint_for(*, actor, organization_id, endpoint_id, lock=False):
    get_organization(actor=actor, organization_id=organization_id, capability="webhook", lock=lock)
    query = WebhookEndpoint.objects.filter(organization_id=organization_id, pk=endpoint_id)
    if lock:
        query = query.select_for_update()
    row = query.first()
    if row is None:
        raise NotFoundError()
    return row


@transaction.atomic
def create_endpoint(*, actor, organization_id, url, event_types, idempotency_key):
    org, _ = active_organization(
        actor=actor, organization_id=organization_id, capability="webhook", lock=True
    )
    destination(url)
    if (
        not event_types
        or len(event_types) > len(EVENT_TYPES)
        or not set(event_types) <= EVENT_TYPES
    ):
        raise DomainError(code="validation_error", message="Choose supported webhook event types.")
    with creation_command(
        actor_id=actor.id,
        scope=f"webhook:create:{org.id}",
        key=idempotency_key,
        values={"url": url, "event_types": sorted(set(event_types))},
    ) as command:
        if command.resource_id:
            return (
                WebhookEndpoint.objects.get(pk=command.resource_id, organization=org),
                None,
                False,
            )
        if WebhookEndpoint.objects.filter(organization=org).count() >= 10:
            raise ConflictError(message="The ten-endpoint safety limit has been reached.")
        raw = "whsec_" + secrets.token_urlsafe(32)
        row = WebhookEndpoint.objects.create(
            organization=org,
            url=url,
            event_types=sorted(set(event_types)),
            encrypted_secret=cipher().encrypt(raw.encode()).decode(),
        )
        record_event(
            action="webhook.created",
            actor_id=actor.id,
            organization_id=org.id,
            target_type="webhooks.WebhookEndpoint",
            target_id=row.id,
        )
        remember_created(command, row.id)
        return row, raw, True


@transaction.atomic
def set_endpoint_status(*, actor, session, organization_id, endpoint_id, is_active, confirm):
    require_recent_login(actor=actor, session=session)
    row = endpoint_for(
        actor=actor, organization_id=organization_id, endpoint_id=endpoint_id, lock=True
    )
    if confirm is not True or type(is_active) is not bool:
        raise DomainError(
            code="confirmation_required", message="Confirm the webhook status change."
        )
    if is_active and row.organization.status != "active":
        raise ConflictError(message="Cannot enable webhooks for an inactive organization.")
    if row.is_active != is_active:
        row.is_active = is_active
        row.save(update_fields=("is_active", "updated_at"))
        record_event(
            action="webhook.status_changed",
            actor_id=actor.id,
            organization_id=organization_id,
            target_type="webhooks.WebhookEndpoint",
            target_id=row.id,
            changes={"is_active": is_active},
        )
    return row


@transaction.atomic
def rotate_secret(*, actor, session, organization_id, endpoint_id, confirm, idempotency_key):
    require_recent_login(actor=actor, session=session)
    row = endpoint_for(
        actor=actor, organization_id=organization_id, endpoint_id=endpoint_id, lock=True
    )
    if confirm is not True:
        raise DomainError(
            code="confirmation_required",
            message="Confirm immediate replacement of the signing secret.",
        )
    with creation_command(
        actor_id=actor.id, scope=f"webhook:rotate:{row.id}", key=idempotency_key, values={}
    ) as command:
        if command.resource_id:
            return row, None
        raw = "whsec_" + secrets.token_urlsafe(32)
        row.encrypted_secret = cipher().encrypt(raw.encode()).decode()
        row.secret_version += 1
        row.save(update_fields=("encrypted_secret", "secret_version", "updated_at"))
        record_event(
            action="webhook.secret_rotated",
            actor_id=actor.id,
            organization_id=organization_id,
            target_type="webhooks.WebhookEndpoint",
            target_id=row.id,
        )
        remember_created(command, row.id)
        return row, raw


def enqueue_event(*, organization_id, event_id, event_type, created_at, data):
    if event_type not in EVENT_TYPES:
        return
    for endpoint in WebhookEndpoint.objects.filter(organization_id=organization_id, is_active=True):
        if event_type in endpoint.event_types:
            WebhookDelivery.objects.get_or_create(
                endpoint=endpoint,
                event_id=event_id,
                defaults={
                    "event_type": event_type,
                    "payload": {
                        "id": str(event_id),
                        "type": event_type,
                        "created_at": created_at.isoformat(),
                        "organization_id": str(organization_id),
                        "data": data,
                    },
                    "next_attempt_at": timezone.now(),
                },
            )


@transaction.atomic
def deliver_one(delivery_id):
    candidate = WebhookDelivery.objects.filter(pk=delivery_id).first()
    if candidate is None or not settings.WEBHOOK_DELIVERY_ENABLED:
        return False
    endpoint = (
        WebhookEndpoint.objects.select_for_update()
        .select_related("organization")
        .get(pk=candidate.endpoint_id)
    )
    row = WebhookDelivery.objects.select_for_update().get(pk=delivery_id)
    if row.status != "pending" or row.next_attempt_at > timezone.now():
        return False
    if not endpoint.is_active or endpoint.organization.status != "active":
        row.status, row.last_error_code = "cancelled", "endpoint_inactive"
        row.save(update_fields=("status", "last_error_code", "updated_at"))
        return False
    row.attempts += 1
    timestamp = int(time.time())
    body = json.dumps(row.payload, sort_keys=True, separators=(",", ":")).encode()
    status, error = None, ""
    try:
        secret = cipher().decrypt(endpoint.encrypted_secret.encode()).decode()
        status = post_json(
            endpoint.url,
            body,
            {
                "X-DevVault-Event-ID": str(row.event_id),
                "X-DevVault-Signature": signature(secret=secret, timestamp=timestamp, body=body),
                "X-DevVault-Secret-Version": str(endpoint.secret_version),
            },
        )
    except UnsafeDestination:
        error = "unsafe_destination"
    except InvalidToken:
        error = "secret_unavailable"
    except OSError, ValueError, DomainError, http.client.HTTPException:
        error = "delivery_unavailable"
    row.last_status_code, row.last_error_code = status, error
    DeliveryAttempt.objects.create(
        delivery=row, number=row.attempts, status_code=status, error_code=error
    )
    if status is not None and 200 <= status < 300:
        row.status, row.delivered_at = "delivered", timezone.now()
    elif (
        row.attempts >= 8
        or error in {"unsafe_destination", "secret_unavailable"}
        or (status and 300 <= status < 500 and status not in {408, 429})
    ):
        row.status = "dead_letter"
    else:
        row.next_attempt_at = timezone.now() + timedelta(
            seconds=min(3600, 10 * 2 ** (row.attempts - 1)) + secrets.randbelow(5)
        )
    row.save(
        update_fields=(
            "attempts",
            "last_status_code",
            "last_error_code",
            "status",
            "delivered_at",
            "next_attempt_at",
            "updated_at",
        )
    )
    return row.status == "delivered"


@transaction.atomic
def retry_delivery(
    *, actor, session, organization_id, endpoint_id, delivery_id, confirm, idempotency_key
):
    require_recent_login(actor=actor, session=session)
    endpoint = endpoint_for(
        actor=actor, organization_id=organization_id, endpoint_id=endpoint_id, lock=True
    )
    row = (
        WebhookDelivery.objects.select_for_update()
        .filter(pk=delivery_id, endpoint=endpoint)
        .first()
    )
    if row is None:
        raise NotFoundError()
    if confirm is not True or not endpoint.is_active or endpoint.organization.status != "active":
        raise ConflictError(message="Confirm retry for an active endpoint.")
    with creation_command(
        actor_id=actor.id, scope=f"webhook:retry:{row.id}", key=idempotency_key, values={}
    ) as command:
        if command.resource_id:
            return row
        if row.status not in {"dead_letter", "cancelled"} or row.attempts >= 32:
            raise ConflictError(
                message="Only failed deliveries under the 32-attempt lifetime cap can be retried."
            )
        row.status, row.next_attempt_at = "pending", timezone.now()
        row.save(update_fields=("status", "next_attempt_at", "updated_at"))
        record_event(
            action="webhook.delivery_retried",
            actor_id=actor.id,
            organization_id=organization_id,
            target_type="webhooks.WebhookDelivery",
            target_id=row.id,
        )
        remember_created(command, row.id)
        return row


def deliver_pending(limit=10):
    if not settings.WEBHOOK_DELIVERY_ENABLED:
        return 0
    identifiers = list(
        WebhookDelivery.objects.filter(status="pending", next_attempt_at__lte=timezone.now())
        .order_by("next_attempt_at")
        .values_list("id", flat=True)[:limit]
    )
    return sum(deliver_one(identifier) for identifier in identifiers)
