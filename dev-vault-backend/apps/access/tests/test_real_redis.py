import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from apps.access.rate_limits import _client, consume_rates
from apps.access.services import create_policy
from apps.credentials.services import issue_key
from apps.projects.tests.test_projects import resources  # noqa: F401

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not os.environ.get("DEVVAULT_TEST_REDIS_URL"), reason="Opt-in real Redis enforcement test"
    ),
]


@pytest.fixture
def limiter(resources, settings):
    settings.REDIS_URL = os.environ["DEVVAULT_TEST_REDIS_URL"]
    owner, org, _, _, service = resources
    key = issue_key(
        actor=owner, service_id=service.id, name="Real Redis test", idempotency_key="redis"
    ).resource
    _organization_id = service.environment.project.organization_id  # hydrate before worker threads
    policies = []

    def policy(algorithm, config):
        row, _ = create_policy(
            actor=owner,
            organization_id=org.id,
            service_id=service.id,
            name="Limiter",
            environment_kind="test",
            algorithm=algorithm,
            dimension="key",
            config=config,
            idempotency_key=algorithm,
        )
        policies.append(row)
        return row

    yield key, service, policy
    # Delete only exact test-owned UUID keys; never flush or scan the user's Redis.
    keys = [f"dv:rate:{{{org.id}}}:test:{p.id}:v{p.version}:{key.family_id}" for p in policies]
    if keys:
        _client(settings.REDIS_URL).delete(*keys)


def test_atomic_fixed_window_concurrent_budget(limiter):
    key, service, policy = limiter
    row = policy("fixed_window", {"limit": 10, "window_seconds": 3600})
    with ThreadPoolExecutor(max_workers=12) as pool:
        decisions = list(
            pool.map(lambda _: consume_rates(policies=[row], key=key, service=service), range(40))
        )
    assert sum(item["allowed"] for item in decisions) == 10
    assert all(item["retry_after"] > 0 for item in decisions if not item["allowed"])


def test_token_bucket_and_multi_policy_atomicity(limiter):
    key, service, policy = limiter
    fixed = policy("fixed_window", {"limit": 2, "window_seconds": 3600})
    bucket = policy("token_bucket", {"capacity": 1, "refill_tokens": 1, "refill_seconds": 1000})
    assert consume_rates(policies=[fixed, bucket], key=key, service=service)["allowed"]
    assert not consume_rates(policies=[fixed, bucket], key=key, service=service)["allowed"]
    # The denied request must not have incremented the otherwise-permitting fixed window.
    assert consume_rates(policies=[fixed], key=key, service=service)["allowed"]
    assert not consume_rates(policies=[fixed], key=key, service=service)["allowed"]
