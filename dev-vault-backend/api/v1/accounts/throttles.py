import hashlib
import time

from django.conf import settings
from django.core.cache import cache
from redis.exceptions import RedisError
from rest_framework.throttling import BaseThrottle

from apps.accounts.exceptions import AccountSecurityUnavailableError


class AccountRequestThrottle(BaseThrottle):
    """Atomic fixed-window counters; proxy-supplied headers are not trusted."""

    def allow_request(self, request, view):
        if request.method != "POST":
            return True
        limit, seconds = settings.ACCOUNT_THROTTLE_RATES[view.throttle_scope]
        now = time.time()
        bucket = int(now // seconds)
        self.retry_after = max(1, (bucket + 1) * seconds - now)
        address = request.META.get("REMOTE_ADDR", "unknown")
        identity = hashlib.sha256(address.encode()).hexdigest()
        key = f"accounts:v1:{view.throttle_scope}:{identity}:{bucket}"
        try:
            # Redis ADD is SET NX and INCR is atomic, including concurrent requests.
            if cache.add(key, 1, timeout=seconds + 1):
                return True
            return cache.incr(key) <= limit
        except (RedisError, OSError, ValueError) as exc:
            # Refuse requests if the authoritative counter cannot be checked.
            raise AccountSecurityUnavailableError() from exc

    def wait(self):
        return self.retry_after
