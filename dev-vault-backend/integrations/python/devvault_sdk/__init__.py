"""Fail-closed, server-side verification client. Never install secrets in browser code."""

import json
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID


class VerificationUnavailable(Exception):
    def __init__(self):
        super().__init__("DevVault verification is unavailable; do not authorize this request.")


class AccessDenied(Exception):
    def __init__(self, code, status, retry_after=0):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(f"DevVault denied access ({code}).")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


@dataclass(frozen=True)
class Decision:
    key_id: str
    service_id: str
    environment: str
    replayed: bool
    rate_limits: list
    quotas: list


@dataclass(frozen=True)
class Client:
    base_url: str
    service_id: str
    environment: str
    audience: str
    integration_secret: str = field(repr=False)
    timeout: float = 3
    allow_insecure_local: bool = False

    def __post_init__(self):
        url = urlsplit(self.base_url)
        local = url.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not (
                url.scheme == "https"
                or (url.scheme == "http" and local and self.allow_insecure_local)
            )
        ):
            raise ValueError("Use HTTPS, or explicitly allow loopback HTTP for development.")
        UUID(self.service_id)
        if (
            self.environment not in {"test", "live"}
            or not self.integration_secret.startswith("dvs_")
            or not 0 < self.timeout <= 30
        ):
            raise ValueError("Invalid DevVault server integration configuration.")

    def verify(
        self, *, api_key, required_scopes, request_id, units=1, method="GET", scope_mode="all"
    ):
        if (
            not isinstance(request_id, str)
            or not 1 <= len(request_id) <= 128
            or any(not 33 <= ord(char) <= 126 for char in request_id)
        ):
            raise ValueError("Use a unique printable ASCII request ID, at most 128 characters.")
        if (
            not isinstance(api_key, str)
            or len(api_key) > 128
            or not api_key.startswith(f"dv_{self.environment}_")
        ):
            raise AccessDenied("invalid_key", 401)
        payload = {
            "service_id": self.service_id,
            "environment": self.environment,
            "audience": self.audience,
            "required_scopes": required_scopes,
            "scope_mode": scope_mode,
            "units": units,
            "method": method,
        }
        request = Request(
            self.base_url.rstrip("/") + "/api/v1/access/verify/",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + api_key,
                "X-DevVault-Service-Token": self.integration_secret,
                "Idempotency-Key": request_id,
            },
        )
        # No automatic redirects, environment proxies, retries, or fail-open cache.
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            try:
                response = opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                response = exc
            with response:
                status = response.code
                content = response.read(65537)
            if len(content) > 65536:
                raise VerificationUnavailable()
            body = json.loads(content)
            if status == 200:
                data = body["data"]
                if (
                    data.get("allowed") is not True
                    or data.get("service_id") != self.service_id
                    or data.get("environment") != self.environment
                    or data.get("audience") != self.audience
                ):
                    raise VerificationUnavailable()
                return Decision(
                    key_id=str(UUID(data["key_id"])),
                    service_id=self.service_id,
                    environment=self.environment,
                    replayed=bool(data["replayed"]),
                    rate_limits=data["rate_limits"],
                    quotas=data["quotas"],
                )
            if status in {401, 403, 429}:
                code = body.get("error", {}).get("code", "access_denied")
                allowed_codes = {
                    "invalid_key",
                    "expired",
                    "revoked",
                    "environment_mismatch",
                    "service_inactive",
                    "invalid_integration_credential",
                    "context_mismatch",
                    "insufficient_scope",
                    "rate_limited",
                    "quota_exceeded",
                    "throttled",
                }
                safe_code = code if code in allowed_codes else "access_denied"
                retry = body.get("error", {}).get("details", {}).get("retry_after", 0)
                raise AccessDenied(
                    safe_code, status, retry if type(retry) is int and retry >= 0 else 0
                )
            raise VerificationUnavailable()
        except (URLError, OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
            raise VerificationUnavailable() from exc
