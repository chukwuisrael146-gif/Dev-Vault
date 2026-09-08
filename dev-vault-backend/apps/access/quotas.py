"""Durable weighted quotas. Call reserve operations inside the verification transaction."""

from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.access.models import QuotaAdjustment, QuotaBucket, QuotaNotice
from apps.access.selectors import get_policy
from apps.accounts.profile_services import require_recent_login
from apps.audit.services import record_event
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.idempotency import creation_command, remember_created
from apps.core.logging import redact_string
from apps.credentials.models import APIKey


def period_bounds(algorithm, now):
    now = now.astimezone(UTC)
    start = datetime(now.year, now.month, now.day if algorithm == "daily" else 1, tzinfo=UTC)
    if algorithm == "daily":
        return start, start + timedelta(days=1)
    return start, datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=UTC)


def locked_bucket(*, policy, dimension_id, now):
    start, end = period_bounds(policy.algorithm, now)
    row, _ = QuotaBucket.objects.get_or_create(
        policy=policy, dimension_id=dimension_id, period_start=start, defaults={"period_end": end}
    )
    return QuotaBucket.objects.select_for_update().get(pk=row.id)


def prepare_quotas(*, policies, key, units, now):
    rows, limits = [], []
    for policy in policies:  # caller resolves policies in deterministic UUID order
        if policy.algorithm not in {"daily", "monthly"}:
            continue
        dimension = key.family_id if policy.dimension == "key" else policy.id
        row = locked_bucket(policy=policy, dimension_id=dimension, now=now)
        allowance = max(0, policy.config["limit"] + row.adjustment)
        remaining = max(0, allowance - row.used)
        limits.append(
            {
                "policy_id": str(policy.id),
                "limit": allowance,
                "remaining": max(0, remaining - units),
                "reset_at": int(row.period_end.timestamp()),
            }
        )
        if row.used + units > allowance:
            return [], {
                "allowed": False,
                "limits": limits,
                "retry_after": max(1, int((row.period_end - now).total_seconds())),
            }
        rows.append(row)
    return rows, {"allowed": True, "limits": limits, "retry_after": 0}


def consume_quotas(*, rows, units):
    for row in rows:
        row.used += units
        row.save(update_fields=("used", "updated_at"))
        allowance = max(0, row.policy.config["limit"] + row.adjustment)
        for threshold in (80, 100):
            if allowance and row.used * 100 >= allowance * threshold:
                _, created = QuotaNotice.objects.get_or_create(bucket=row, threshold=threshold)
                if created:
                    record_event(
                        action="quota.threshold_reached",
                        organization_id=row.policy.organization_id,
                        target_type="access.QuotaBucket",
                        target_id=row.id,
                        changes={
                            "policy_id": str(row.policy_id),
                            "threshold": threshold,
                            "used": row.used,
                            "allowance": allowance,
                        },
                    )


@transaction.atomic
def adjust_quota(
    *, actor, session, policy_id, delta, reason, confirm, idempotency_key, dimension_id=None
):
    require_recent_login(actor=actor, session=session)
    policy, _ = get_policy(actor=actor, policy_id=policy_id, capability="quota_adjust", lock=True)
    if policy.algorithm not in {"daily", "monthly"}:
        raise DomainError(
            code="validation_error",
            message="Only daily or monthly quota allowances can be adjusted.",
        )
    if (
        confirm is not True
        or type(delta) is not int
        or not 0 < abs(delta) <= 10**12
        or not 5 <= len(reason) <= 256
        or redact_string(reason) != reason
    ):
        raise DomainError(
            code="validation_error",
            message="Confirm a nonzero adjustment with a non-secret reason.",
        )
    if policy.dimension == "shared":
        if dimension_id is not None and dimension_id != policy.id:
            raise NotFoundError()
        dimension_id = policy.id
    else:
        keys = APIKey.objects.filter(
            family_id=dimension_id,
            service__environment__project__organization_id=policy.organization_id,
            service__environment__kind=policy.environment_kind,
        )
        if policy.project_id:
            keys = keys.filter(service__environment__project_id=policy.project_id)
        if policy.service_id:
            keys = keys.filter(service_id=policy.service_id)
        if policy.key_family_id:
            keys = keys.filter(family_id=policy.key_family_id)
        if dimension_id is None or not keys.exists():
            raise NotFoundError()
    with creation_command(
        actor_id=actor.id,
        scope=f"quota:adjust:{policy.id}",
        key=idempotency_key,
        values={"dimension_id": dimension_id, "delta": delta, "reason": reason},
    ) as command:
        if command.resource_id:
            return QuotaAdjustment.objects.get(pk=command.resource_id), False
        bucket = locked_bucket(policy=policy, dimension_id=dimension_id, now=timezone.now())
        if abs(bucket.adjustment + delta) > 10**12:
            raise ConflictError(message="The period adjustment safety limit would be exceeded.")
        row = QuotaAdjustment.objects.create(bucket=bucket, actor=actor, delta=delta, reason=reason)
        bucket.adjustment += delta
        bucket.save(update_fields=("adjustment", "updated_at"))
        record_event(
            action="quota.adjusted",
            actor_id=actor.id,
            target_type="access.QuotaAdjustment",
            target_id=row.id,
            organization_id=policy.organization_id,
            changes={"delta": delta, "policy_id": str(policy.id)},
        )
        remember_created(command, row.id)
        return row, True
