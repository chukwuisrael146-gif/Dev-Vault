"""Strict parsing and versioned keyed verifiers for 256-bit random credentials."""

import hashlib
import hmac
import re
import secrets
from uuid import UUID

from django.conf import settings

from apps.core.exceptions import DomainError


class InvalidCredential(DomainError):
    code = "invalid_key"
    message = "The supplied credential is invalid."
    status_code = 401


KEY_PATTERN = re.compile(r"dv_(test|live)_([a-f0-9]{32})_([A-Za-z0-9_-]{43})\Z")
INTEGRATION_PATTERN = re.compile(r"dvs_([a-f0-9]{32})_([A-Za-z0-9_-]{43})\Z")


def generate_key(identifier: UUID, environment: str) -> str:
    if environment not in {"test", "live"}:
        raise ValueError("Unknown environment")
    return f"dv_{environment}_{identifier.hex}_{secrets.token_urlsafe(32)}"


def generate_integration_credential(identifier: UUID) -> str:
    return f"dvs_{identifier.hex}_{secrets.token_urlsafe(32)}"


def parse_key(raw: str) -> tuple[str, UUID]:
    if not isinstance(raw, str) or len(raw) > 128:
        raise InvalidCredential()
    match = KEY_PATTERN.fullmatch(raw)
    if not match:
        raise InvalidCredential()
    return match[1], UUID(hex=match[2])


def parse_integration_credential(raw: str) -> UUID:
    if not isinstance(raw, str) or len(raw) > 128:
        raise InvalidCredential(code="invalid_integration_credential")
    match = INTEGRATION_PATTERN.fullmatch(raw)
    if not match:
        raise InvalidCredential(code="invalid_integration_credential")
    return UUID(hex=match[1])


def digest(raw: str, version: str) -> str:
    return hmac.new(
        settings.API_KEY_PEPPERS[version].encode(), raw.encode(), hashlib.sha256
    ).hexdigest()


def matches(raw: str, verifier: str, version: str) -> bool:
    if version not in settings.API_KEY_PEPPERS:
        return False
    return hmac.compare_digest(digest(raw, version), verifier)
