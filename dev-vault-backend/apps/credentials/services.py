from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.profile_services import require_recent_login
from apps.audit.services import record_event
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.idempotency import creation_command, remember_created
from apps.core.logging import redact_string
from apps.credentials.hashing import (
    InvalidCredential,
    digest,
    generate_integration_credential,
    generate_key,
    matches,
    parse_integration_credential,
    parse_key,
)
from apps.credentials.models import APIKey, IntegrationCredential
from apps.credentials.selectors import get_key
from apps.organizations.permissions import require_capability
from apps.projects.models import APIService
from apps.projects.selectors import get_service


@dataclass(frozen=True)
class IssuedCredential:
    resource: APIKey | IntegrationCredential
    raw_value: str | None = field(repr=False)
    created: bool = True


def _label(name):
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 128
        or redact_string(name) != name
    ):
        raise DomainError(
            code="validation_error", message="Use a non-secret name of 1–128 characters."
        )


def _expiry(value):
    now = timezone.now()
    if value is None:
        return now + timedelta(days=30)
    if timezone.is_naive(value) or not now < value <= now + timedelta(days=365):
        raise DomainError(
            code="validation_error", message="Expiry must be in the next 365 days with a timezone."
        )
    return value


def _audit(action, key, actor=None, changes=None):
    record_event(
        action=action,
        actor_id=actor.id if actor else None,
        target_id=key.id,
        target_type=f"credentials.{type(key).__name__}",
        organization_id=key.service.environment.project.organization_id,
        changes=changes,
    )


def _create_key(*, actor, service, name, consumer_reference, expires_at):
    key = APIKey(
        service=service,
        created_by=actor,
        name=name.strip(),
        consumer_reference=consumer_reference,
        expires_at=expires_at,
        pepper_version=settings.API_KEY_ACTIVE_PEPPER_VERSION,
    )
    raw = generate_key(key.id, service.environment.kind)
    key.verifier = digest(raw, key.pepper_version)
    key.display_prefix = f"dv_{service.environment.kind}_{key.id.hex[:8]}"
    key.last_four = raw[-4:]
    key.save(force_insert=True)
    return key, raw


@transaction.atomic
def issue_key(
    *,
    actor,
    service_id,
    name,
    idempotency_key,
    expires_at=None,
    consumer_reference="",
    permission_ids=(),
):
    service, member = get_service(
        actor=actor, service_id=service_id, capability="key", active=True, lock=True
    )
    if service.environment.kind == "live":
        require_capability(member.role, "live_key")
    _label(name)
    if consumer_reference:
        _label(consumer_reference)
    if len(permission_ids) > 100:
        raise DomainError(
            code="validation_error", message="At most 100 permissions may be assigned."
        )
    with creation_command(
        actor_id=actor.id,
        scope=f"key:issue:{service.id}",
        key=idempotency_key,
        values={
            "name": name,
            "expires_at": expires_at,
            "consumer_reference": consumer_reference,
            "permission_ids": sorted(str(p) for p in permission_ids),
        },
    ) as command:
        if command.resource_id:
            return IssuedCredential(
                get_key(actor=actor, key_id=command.resource_id)[0], None, False
            )
        key, raw = _create_key(
            actor=actor,
            service=service,
            name=name,
            consumer_reference=consumer_reference,
            expires_at=_expiry(expires_at),
        )
        # Access owns grants; lazy import avoids a model/import dependency cycle.
        if permission_ids:
            from apps.access.services import assign_key_permissions

            assign_key_permissions(actor=actor, key_id=key.id, permission_ids=permission_ids)
        _audit("key.created", key, actor)
        remember_created(command, key.id)
        return IssuedCredential(key, raw)


@transaction.atomic
def revoke_key(*, actor, session, key_id, confirm, reason="revoked"):
    require_recent_login(actor=actor, session=session)
    key, member = get_key(actor=actor, key_id=key_id, capability="key", lock=True)
    if key.service.environment.kind == "live":
        require_capability(member.role, "live_key")
    if confirm is not True or reason not in {"revoked", "compromised", "retired"}:
        raise DomainError(
            code="confirmation_required", message="Confirm revocation with a supported reason."
        )
    if not key.revoked_at:
        key.revoked_at = timezone.now()
        key.revocation_reason = reason
        key.save(update_fields=("revoked_at", "revocation_reason", "updated_at"))
        _audit("key.revoked", key, actor, {"reason": reason})
    return key


@transaction.atomic
def rotate_key(*, actor, session, key_id, idempotency_key, confirm, overlap_seconds=0):
    require_recent_login(actor=actor, session=session)
    key, member = get_key(
        actor=actor, key_id=key_id, capability="key", active_parent=True, lock=True
    )
    if key.service.environment.kind == "live":
        require_capability(member.role, "live_key")
    if confirm is not True or type(overlap_seconds) is not int or not 0 <= overlap_seconds <= 86400:
        raise DomainError(
            code="validation_error", message="Confirm rotation with an overlap of 0–86400 seconds."
        )
    with creation_command(
        actor_id=actor.id,
        scope=f"key:rotate:{key.id}",
        key=idempotency_key,
        values={"overlap_seconds": overlap_seconds},
    ) as command:
        if command.resource_id:
            return IssuedCredential(
                get_key(actor=actor, key_id=command.resource_id)[0], None, False
            )
        if key.revoked_at or key.expires_at <= timezone.now() or key.successor_id:
            raise ConflictError(message="Only a current, unrotated key can be rotated.")
        replacement, raw = _create_key(
            actor=actor,
            service=key.service,
            name=key.name,
            consumer_reference=key.consumer_reference,
            expires_at=key.expires_at,
        )
        replacement.family_id = key.family_id
        replacement.save(update_fields=("family_id", "updated_at"))
        # Once access is installed it owns copying both grants and explicit policy bindings.
        from django.apps import apps

        if apps.is_installed("apps.access"):
            from apps.access.services import copy_key_access

            copy_key_access(actor=actor, predecessor=key, successor=replacement)
        key.successor = replacement
        now = timezone.now()
        if overlap_seconds:
            key.expires_at = min(key.expires_at, now + timedelta(seconds=overlap_seconds))
        else:
            key.revoked_at, key.revocation_reason = now, "rotated"
        key.save(
            update_fields=(
                "successor",
                "expires_at",
                "revoked_at",
                "revocation_reason",
                "updated_at",
            )
        )
        _audit(
            "key.rotated",
            key,
            actor,
            {"successor_id": str(replacement.id), "overlap_seconds": overlap_seconds},
        )
        remember_created(command, replacement.id)
        return IssuedCredential(replacement, raw)


@transaction.atomic
def issue_integration_credential(*, actor, service_id, name, idempotency_key):
    service, member = get_service(
        actor=actor, service_id=service_id, capability="key", active=True, lock=True
    )
    if service.environment.kind == "live":
        require_capability(member.role, "live_key")
    _label(name)
    with creation_command(
        actor_id=actor.id,
        scope=f"integration:issue:{service.id}",
        key=idempotency_key,
        values={"name": name},
    ) as command:
        if command.resource_id:
            return IssuedCredential(
                IntegrationCredential.objects.get(pk=command.resource_id, service=service),
                None,
                False,
            )
        row = IntegrationCredential(
            service=service,
            created_by=actor,
            name=name.strip(),
            pepper_version=settings.API_KEY_ACTIVE_PEPPER_VERSION,
            expires_at=timezone.now() + timedelta(days=90),
        )
        raw = generate_integration_credential(row.id)
        row.verifier = digest(raw, row.pepper_version)
        row.save(force_insert=True)
        _audit("integration_credential.created", row, actor)
        remember_created(command, row.id)
        return IssuedCredential(row, raw)


@transaction.atomic
def revoke_integration_credential(*, actor, session, service_id, credential_id, confirm):
    require_recent_login(actor=actor, session=session)
    service, member = get_service(actor=actor, service_id=service_id, capability="key", lock=True)
    if service.environment.kind == "live":
        require_capability(member.role, "live_key")
    row = (
        IntegrationCredential.objects.select_for_update()
        .filter(service=service, pk=credential_id)
        .first()
    )
    if row is None:
        raise NotFoundError()
    if confirm is not True:
        raise DomainError(
            code="confirmation_required", message="Explicit confirmation is required."
        )
    if not row.revoked_at:
        row.revoked_at = timezone.now()
        row.save(update_fields=("revoked_at", "updated_at"))
        _audit("integration_credential.revoked", row, actor)


def service_is_active(service: APIService) -> bool:
    environment = service.environment
    return (
        service.is_active
        and environment.is_active
        and environment.project.archived_at is None
        and environment.project.organization.status == "active"
    )


def authenticate_integration(raw: str) -> IntegrationCredential:
    identifier = parse_integration_credential(raw)
    credential = (
        IntegrationCredential.objects.select_related("service__environment__project__organization")
        .filter(pk=identifier)
        .first()
    )
    if (
        credential is None
        or not matches(raw, credential.verifier, credential.pepper_version)
        or credential.revoked_at
        or credential.expires_at <= timezone.now()
        or not service_is_active(credential.service)
    ):
        raise InvalidCredential(code="invalid_integration_credential")
    return credential


def authenticate_key(*, raw: str, service: APIService) -> APIKey:
    environment, identifier = parse_key(raw)
    key = APIKey.objects.filter(pk=identifier, service=service).first()
    if key is None or not matches(raw, key.verifier, key.pepper_version):
        raise InvalidCredential()
    if environment != service.environment.kind:
        raise InvalidCredential(code="environment_mismatch")
    if key.revoked_at:
        raise InvalidCredential(code="revoked")
    if key.expires_at <= timezone.now():
        raise InvalidCredential(code="expired")
    if not service_is_active(service):
        raise InvalidCredential(code="service_inactive")
    return key
