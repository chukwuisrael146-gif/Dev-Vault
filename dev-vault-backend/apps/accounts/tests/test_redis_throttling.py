import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db(transaction=True)
def test_real_redis_atomic_account_throttle():
    redis_url = os.environ.get("TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("Set TEST_REDIS_URL for the isolated-key Redis integration test")
    clock = time.time()
    seconds = 60
    identity = hashlib.sha256(b"127.0.0.1").hexdigest()
    key = f"accounts:v1:refresh:{identity}:{int(clock // seconds)}"
    with override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": redis_url,
                "KEY_PREFIX": "devvault-integration-" + uuid4().hex,
                "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
            }
        },
        ACCOUNT_THROTTLE_RATES={"refresh": (2, seconds)},
    ):
        try:

            def request(_):
                return (
                    APIClient()
                    .post(
                        reverse("accounts:refresh"),
                        {"refresh_token": "bad"},
                        format="json",
                    )
                    .status_code
                )

            with (
                patch("api.v1.accounts.throttles.time.time", return_value=clock),
                ThreadPoolExecutor(max_workers=10) as pool,
            ):
                responses = list(pool.map(request, range(10)))
            assert responses.count(401) == 2
            assert responses.count(429) == 8
        finally:
            # Delete only this test's uniquely namespaced counter; never FLUSHDB.
            cache.delete(key)
