import re

from django.db import transaction

from apps.access.models import APIKeyPermission, Permission, Policy, PolicyRevision
from apps.access.selectors import get_policy
from apps.accounts.profile_services import require_recent_login
from apps.audit.services import record_event
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.idempotency import creation_command, remember_created
from apps.core.logging import redact_string
from apps.credentials.selectors import get_key
from apps.organizations.permissions import require_capability
from apps.organizations.selectors import active_organization
from apps.projects.selectors import get_project, get_service

SCOPE_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,31}[:.][a-z][a-z0-9_-]{0,62}\Z")


def validate_scopes(scopes):
    if (
        not isinstance(scopes, (list, tuple))
        or len(scopes) > 100
        or any(not isinstance(value, str) or not SCOPE_PATTERN.fullmatch(value) for value in scopes)
    ):
        raise DomainError(
            code="validation_error", message="Use at most 100 exact namespaced scopes."
        )
    return sorted(set(scopes))


def _live(member, kind):
    if kind == "live":
        require_capability(member.role, "live_key")


def _audit(action, row, actor, organization_id, changes=None):
    record_event(
        action=action,
        actor_id=actor.id,
        target_id=row.id,
        target_type=f"access.{type(row).__name__}",
        organization_id=organization_id,
        changes=changes,
    )


@transaction.atomic
def create_permission(*, actor, service_id, name, description="", idempotency_key):
    service, member = get_service(
        actor=actor, service_id=service_id, capability="policy", active=True, lock=True
    )
    _live(member, service.environment.kind)
    validate_scopes([name])
    if len(description) > 256 or redact_string(description) != description:
        raise DomainError(
            code="validation_error",
            message="Use a non-secret description of at most 256 characters.",
        )
    with creation_command(
        actor_id=actor.id,
        scope=f"permission:create:{service.id}",
        key=idempotency_key,
        values={"name": name, "description": description},
    ) as command:
        if command.resource_id:
            return Permission.objects.get(pk=command.resource_id, service=service), False
        if Permission.objects.filter(service=service, name=name).exists():
            raise ConflictError(message="This scope already exists in the service.")
        row = Permission.objects.create(service=service, name=name, description=description)
        _audit("permission.created", row, actor, service.environment.project.organization_id)
        remember_created(command, row.id)
        return row, True


@transaction.atomic
def set_permission_status(*, actor, session, service_id, permission_id, is_active, confirm):
    require_recent_login(actor=actor, session=session)
    service, member = get_service(
        actor=actor, service_id=service_id, capability="policy", lock=True
    )
    _live(member, service.environment.kind)
    row = Permission.objects.select_for_update().filter(pk=permission_id, service=service).first()
    if row is None:
        raise NotFoundError()
    if confirm is not True or type(is_active) is not bool:
        raise DomainError(code="confirmation_required", message="Confirm the scope status change.")
    if row.is_active != is_active:
        row.is_active = is_active
        row.save(update_fields=("is_active", "updated_at"))
        _audit(
            "permission.status_changed",
            row,
            actor,
            service.environment.project.organization_id,
            {"is_active": is_active},
        )
    return row


@transaction.atomic
def assign_key_permissions(*, actor, key_id, permission_ids, session=None, confirm=False):
    key, member = get_key(
        actor=actor, key_id=key_id, capability="key", active_parent=True, lock=True
    )
    _live(member, key.service.environment.kind)
    identifiers = set(permission_ids)
    if len(permission_ids) > 100:
        raise DomainError(
            code="validation_error", message="At most 100 permissions may be assigned."
        )
    allowed = list(
        Permission.objects.filter(service_id=key.service_id, id__in=identifiers, is_active=True)
    )
    if len(allowed) != len(identifiers):
        raise NotFoundError(message="One or more permissions are unavailable in this service.")
    existing = set(key.grants.values_list("permission_id", flat=True))
    removed = existing - identifiers
    if removed:
        require_recent_login(actor=actor, session=session)
        if confirm is not True:
            raise DomainError(
                code="confirmation_required", message="Confirm removal of existing scope grants."
            )
    key.grants.filter(permission_id__in=removed).delete()
    APIKeyPermission.objects.bulk_create(
        [APIKeyPermission(key=key, permission=p) for p in allowed if p.id not in existing]
    )
    _audit(
        "key.permissions_changed",
        key,
        actor,
        key.service.environment.project.organization_id,
        {
            "added_ids": sorted(str(p) for p in identifiers - existing),
            "removed_ids": sorted(str(p) for p in removed),
        },
    )
    return key


def copy_key_access(*, actor, predecessor, successor):
    # Key-specific policies target family_id, already inherited by the successor.
    APIKeyPermission.objects.bulk_create(
        [
            APIKeyPermission(key=successor, permission_id=p)
            for p in predecessor.grants.values_list("permission_id", flat=True)
        ]
    )


def validate_policy_config(algorithm, config):
    fields = {
        "fixed_window": {"limit": 10**9, "window_seconds": 86400},
        "token_bucket": {"capacity": 10**9, "refill_tokens": 10**9, "refill_seconds": 86400},
        "daily": {"limit": 10**12},
        "monthly": {"limit": 10**12},
    }.get(algorithm)
    if (
        fields is None
        or not isinstance(config, dict)
        or set(config) != set(fields)
        or any(
            type(config[field]) is not int or not 1 <= config[field] <= maximum
            for field, maximum in (fields or {}).items()
        )
    ):
        raise DomainError(
            code="validation_error",
            message="Invalid policy parameters; use the documented bounded positive integers.",
        )

    if (
        algorithm == "token_bucket"
        and config["capacity"] * config["refill_seconds"] > 86400 * config["refill_tokens"]
    ):
        raise DomainError(
            code="validation_error", message="A token bucket must fully refill within one day."
        )


def _revision(policy, actor):
    PolicyRevision.objects.create(
        policy=policy,
        version=policy.version,
        actor=actor,
        snapshot={
            "name": policy.name,
            "algorithm": policy.algorithm,
            "dimension": policy.dimension,
            "config": policy.config,
            "is_active": policy.is_active,
        },
    )


@transaction.atomic
def create_policy(
    *,
    actor,
    organization_id,
    name,
    environment_kind,
    algorithm,
    dimension,
    config,
    idempotency_key,
    project_id=None,
    service_id=None,
    key_id=None,
):
    org, member = active_organization(
        actor=actor, organization_id=organization_id, capability="policy", lock=True
    )
    _live(member, environment_kind)
    if environment_kind not in {"test", "live"} or dimension not in {"shared", "key"}:
        raise DomainError(
            code="validation_error", message="Unsupported policy environment or dimension."
        )
    if (
        not isinstance(name, str)
        or not 1 <= len(name.strip()) <= 128
        or redact_string(name) != name
    ):
        raise DomainError(
            code="validation_error", message="Use a non-secret name of 1–128 characters."
        )
    validate_policy_config(algorithm, config)
    family_id = None
    if key_id:
        key, _ = get_key(actor=actor, key_id=key_id)
        if service_id and service_id != key.service_id:
            raise NotFoundError()
        service_id, family_id = key.service_id, key.family_id
    if service_id:
        service, _ = get_service(actor=actor, service_id=service_id, active=True)
        if service.environment.kind != environment_kind or (
            project_id and project_id != service.environment.project_id
        ):
            raise NotFoundError()
        project_id = service.environment.project_id
    if project_id:
        project, _ = get_project(actor=actor, project_id=project_id, active=True)
        if project.organization_id != org.id:
            raise NotFoundError()
    values = dict(
        name=name,
        environment_kind=environment_kind,
        algorithm=algorithm,
        dimension=dimension,
        config=config,
        project_id=project_id,
        service_id=service_id,
        key_family_id=family_id,
    )
    with creation_command(
        actor_id=actor.id, scope=f"policy:create:{org.id}", key=idempotency_key, values=values
    ) as command:
        if command.resource_id:
            return Policy.objects.get(pk=command.resource_id, organization=org), False
        # Bound worst-case resolution and script work. Raise deliberately, never truncate policies.
        if (
            Policy.objects.filter(
                organization=org, environment_kind=environment_kind, is_active=True
            ).count()
            >= 64
        ):
            raise ConflictError(
                message="This environment has reached the 64 active-policy safety limit."
            )
        policy = Policy.objects.create(organization=org, **values)
        _revision(policy, actor)
        _audit("policy.created", policy, actor, org.id)
        remember_created(command, policy.id)
        return policy, True


@transaction.atomic
def update_policy(
    *, actor, session, policy_id, expected_version, confirm, config=None, is_active=None, name=None
):
    require_recent_login(actor=actor, session=session)
    policy, member = get_policy(actor=actor, policy_id=policy_id, capability="policy", lock=True)
    _live(member, policy.environment_kind)
    if confirm is not True:
        raise DomainError(code="confirmation_required", message="Confirm the policy change.")
    if expected_version != policy.version:
        raise ConflictError(code="stale_policy", message="Reload the policy before editing it.")
    if config is not None:
        validate_policy_config(policy.algorithm, config)
        policy.config = config
    if is_active is not None:
        if type(is_active) is not bool:
            raise DomainError(code="validation_error", message="is_active must be a boolean.")
        if (
            is_active
            and not policy.is_active
            and Policy.objects.filter(
                organization_id=policy.organization_id,
                environment_kind=policy.environment_kind,
                is_active=True,
            ).count()
            >= 64
        ):
            raise ConflictError(message="The active-policy safety limit has been reached.")
        policy.is_active = is_active
    if name is not None:
        if not 1 <= len(name.strip()) <= 128 or redact_string(name) != name:
            raise DomainError(code="validation_error", message="Invalid policy name.")
        policy.name = name.strip()
    policy.version += 1
    policy.save(update_fields=("config", "is_active", "name", "version", "updated_at"))
    _revision(policy, actor)
    _audit(
        "policy.updated",
        policy,
        actor,
        policy.organization_id,
        {"version": policy.version, "is_active": policy.is_active},
    )
    return policy
