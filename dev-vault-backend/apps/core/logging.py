import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from apps.core.context import correlation_id_context

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "raw_key",
        "raw_value",
        "integration_credential",
        "x_devvault_service_token",
        "authorization",
        "cookie",
        "password",
        "new_password",
        "current_password",
        "password_confirmation",
        "verification_token",
        "refresh_token",
        "access_token",
        "secret",
        "encrypted_secret",
        "metrics_token",
        "webhook_encryption_keys",
        "api_key_peppers",
        "set_cookie",
        "token",
    }
)
SECRET_PATTERNS = (
    re.compile(r"\bwhsec_[A-Za-z0-9_-]+"),
    re.compile(r"\bdvs_[A-Za-z0-9_-]+"),
    re.compile(r"\bdv_(?:verify|reset|invite)_[A-Za-z0-9_:%-]+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bdv_(?:test|live)_[A-Za-z0-9_-]+_[A-Za-z0-9_-]+\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(
        r"(?i)(authorization|password|secret|token|api[_-]?key|cookie)"
        r"\s*[:=]\s*([^\s,;]+)"
    ),
)


def redact_string(value: str) -> str:
    sanitized = value
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            sanitized = pattern.sub(lambda match: f"{match.group(1)}={REDACTED}", sanitized)
        else:
            sanitized = pattern.sub(REDACTED, sanitized)
    return sanitized


def redact_value(value: Any, *, key: str | None = None) -> Any:
    if key and key.casefold().replace("-", "_") in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, dict):
        return {item_key: redact_value(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_value(record.msg)
        record.args = redact_value(record.args)
        return True


class SafeJsonFormatter(logging.Formatter):
    allowed_extra_fields = (
        "actor_id",
        "dependency",
        "error_type",
        "latency_ms",
        "method",
        "outcome",
        "route",
        "status_code",
        "tenant_id",
    )

    def __init__(self, *, service: str, environment: str, deployment_version: str) -> None:
        super().__init__()
        self.service = service
        self.environment = environment
        self.deployment_version = deployment_version

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "service": self.service,
            "environment": self.environment,
            "deployment_version": self.deployment_version,
            "logger": record.name,
            "message": redact_string(record.getMessage()),
            "request_id": correlation_id_context.get(),
        }
        for field in self.allowed_extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = redact_value(value, key=field)
        if record.exc_info:
            payload["exception"] = redact_string(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, separators=(",", ":"))
