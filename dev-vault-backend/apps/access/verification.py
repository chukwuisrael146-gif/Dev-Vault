"""Verification orchestration; the trusted customer backend owns business authorization.

A durable decision reserves quota before returning allow. Redis is not in the
SQL transaction: a failed SQL commit can conservatively consume rate capacity,
but can never return allow or commit quota without its corresponding event.
"""

import time

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.access.models import Permission
from apps.access.quotas import consume_quotas, prepare_quotas
from apps.access.rate_limits import consume_rates
from apps.access.selectors import applicable_policies
from apps.access.services import validate_scopes
from apps.core.exceptions import ConflictError, DomainError
from apps.core.idempotency import creation_command, remember_created
from apps.credentials.hashing import InvalidCredential
from apps.credentials.models import APIKey
from apps.credentials.services import authenticate_integration, authenticate_key
from apps.usage.models import QuotaReservation, UsageEvent


def _denied(code, status=403, limits=None):
    return {
        "allowed": False,
        "code": code,
        "rate_limits": [],
        "quotas": [],
        "retry_after": 0,
        **(limits or {}),
    }, status


def verify_access(
    *,
    integration_secret,
    raw_key,
    service_id,
    environment,
    audience,
    required_scopes,
    idempotency_key,
    scope_mode="all",
    units=1,
    method="GET",
):
    started = time.monotonic()
    integration = authenticate_integration(integration_secret)
    service = integration.service
    scopes = validate_scopes(required_scopes)
    if scope_mode not in {"all", "any"} or type(units) is not int or not 1 <= units <= 1000000:
        raise DomainError(
            code="validation_error", message="Invalid scope mode or weighted usage units."
        )
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise DomainError(code="validation_error", message="Unsupported HTTP method.")
    if (
        service.id != service_id
        or service.environment.kind != environment
        or service.audience != audience
    ):
        raise InvalidCredential(
            code="context_mismatch",
            message="The integration credential does not match this service context.",
        )
    key, credential_error = None, None
    try:
        key = authenticate_key(raw=raw_key, service=service)
    except InvalidCredential as exc:
        credential_error = exc.code
    # Keyed fingerprint only; neither credential nor reversible body is stored.
    fingerprint = salted_hmac(
        "devvault.verify.credential.v1", raw_key, algorithm="sha256"
    ).hexdigest()
    with transaction.atomic():
        if key:
            APIKey.objects.select_for_update().get(pk=key.id)
            # Recheck after acquiring the revocation/rotation mutex.
            try:
                key = authenticate_key(raw=raw_key, service=service)
            except InvalidCredential as exc:
                credential_error = exc.code
        granted = (
            set(
                Permission.objects.filter(
                    grants__key=key, service=service, is_active=True
                ).values_list("name", flat=True)
            )
            if key
            else set()
        )
        scope_allowed = (
            all(s in granted for s in scopes)
            if scope_mode == "all"
            else bool(set(scopes) & granted)
        )
        if not scopes:
            scope_allowed = True  # Explicit authenticate-only request from the trusted integration.
        with creation_command(
            actor_id=service.id,
            scope="access:verify:v1",
            key=idempotency_key,
            values={
                "credential_fingerprint": fingerprint,
                "service_id": service_id,
                "environment": environment,
                "audience": audience,
                "scopes": scopes,
                "scope_mode": scope_mode,
                "units": units,
                "method": method,
            },
        ) as command:
            if command.resource_id:
                # Replays require current authentication and scope grants.
                if credential_error:
                    return (*_denied(credential_error, 401), True)
                if not scope_allowed:
                    return (*_denied("insufficient_scope"), True)
                event = UsageEvent.objects.get(pk=command.resource_id, service=service)
                return event.decision, event.status_code, True
            quota_rows = []
            if credential_error:
                decision, status = _denied(credential_error, 401)
            elif not scope_allowed:
                decision, status = _denied("insufficient_scope")
            else:
                policies = list(applicable_policies(key=key, service=service).select_for_update())
                if len(policies) > 64:
                    raise ConflictError(message="The policy safety limit has been exceeded.")
                now = timezone.now()
                quota_rows, quota = prepare_quotas(policies=policies, key=key, units=units, now=now)
                if not quota["allowed"]:
                    decision, status = _denied(
                        "quota_exceeded",
                        429,
                        {"quotas": quota["limits"], "retry_after": quota["retry_after"]},
                    )
                else:
                    rate = consume_rates(policies=policies, key=key, service=service)
                    if not rate["allowed"]:
                        decision, status = _denied(
                            "rate_limited",
                            429,
                            {"rate_limits": rate["limits"], "retry_after": rate["retry_after"]},
                        )
                    else:
                        consume_quotas(rows=quota_rows, units=units)
                        decision, status = (
                            {
                                "allowed": True,
                                "code": "allowed",
                                "key_id": str(key.id),
                                "service_id": str(service.id),
                                "environment": environment,
                                "audience": audience,
                                "rate_limits": rate["limits"],
                                "quotas": quota["limits"],
                                "retry_after": 0,
                            },
                            200,
                        )
                        APIKey.objects.filter(pk=key.id).update(last_used_at=now)
            event = UsageEvent.objects.create(
                service=service,
                key_id=key.id if key else None,
                family_id=key.family_id if key else None,
                method=method,
                outcome=decision["code"],
                units=units if decision["allowed"] else 0,
                latency_ms=min(2**31 - 1, int((time.monotonic() - started) * 1000)),
                decision=decision,
                status_code=status,
            )
            if decision["allowed"]:
                QuotaReservation.objects.bulk_create(
                    [QuotaReservation(event=event, bucket=row, units=units) for row in quota_rows]
                )
            remember_created(command, event.id)
            return decision, status, False
