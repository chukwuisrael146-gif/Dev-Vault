"""Atomic all-or-nothing Redis rate consumption; no silent fail-open fallback."""

import json
from functools import lru_cache

import redis
from django.conf import settings

from apps.core.exceptions import DependencyUnavailableError

SCRIPT = r"""
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local specs = cjson.decode(ARGV[1])
local states = {}
local denied = false
local retry = 0
local result = {}
for i, spec in ipairs(specs) do
    local state = {ttl=1}
    local remaining, reset
    if spec.algorithm == 'fixed_window' then
        local window = math.floor(now / spec.config.window_seconds)
        local stored = redis.call('HMGET', KEYS[i], 'window', 'count')
        local count = 0
        if tonumber(stored[1]) == window then count = tonumber(stored[2]) or 0 end
        reset = (window + 1) * spec.config.window_seconds
        state.window, state.count = window, count + 1
        state.ttl = math.ceil(reset - now) + 1
        remaining = math.max(0, spec.config.limit - count - 1)
        if count >= spec.config.limit then
            denied = true
            retry = math.max(retry, math.ceil(reset - now))
        end
    else
        local stored = redis.call('HMGET', KEYS[i], 'tokens', 'at')
        local rate = spec.config.refill_tokens / spec.config.refill_seconds
        local tokens = tonumber(stored[1]) or spec.config.capacity
        local at = tonumber(stored[2]) or now
        tokens = math.min(spec.config.capacity, tokens + math.max(0, now - at) * rate)
        state.tokens, state.at = math.max(0, tokens - 1), now
        state.ttl = math.max(1, math.ceil(spec.config.capacity / rate) + 1)
        remaining = math.floor(math.max(0, tokens - 1))
        reset = now + (spec.config.capacity - state.tokens) / rate
        if tokens < 1 then
            denied = true
            retry = math.max(retry, math.ceil((1 - tokens) / rate))
        end
    end
    states[i] = state
    result[i] = {policy_id=spec.id, remaining=remaining, reset_at=math.ceil(reset),
                 limit=spec.config.limit or spec.config.capacity}
end
if not denied then
    for i, state in ipairs(states) do
        if state.window then
            redis.call('HSET', KEYS[i], 'window', state.window, 'count', state.count)
        else
            redis.call('HSET', KEYS[i], 'tokens', state.tokens, 'at', state.at)
        end
        redis.call('EXPIRE', KEYS[i], state.ttl)
    end
end
return cjson.encode({allowed=not denied, retry_after=retry, limits=result})
"""


@lru_cache(maxsize=4)
def _client(url):
    return redis.Redis.from_url(
        url, socket_connect_timeout=1, socket_timeout=1, retry_on_timeout=False
    )


def consume_rates(*, policies, key, service):
    organization_id = service.environment.project.organization_id
    specs, keys = [], []
    for policy in policies:
        if policy.algorithm not in {"fixed_window", "token_bucket"}:
            continue
        dimension = key.family_id if policy.dimension == "key" else policy.id
        keys.append(
            f"dv:rate:{{{organization_id}}}:{policy.environment_kind}:{policy.id}:v{policy.version}:{dimension}"
        )
        specs.append({"id": str(policy.id), "algorithm": policy.algorithm, "config": policy.config})
    try:
        client = _client(settings.REDIS_URL)
        if not specs:
            client.ping()  # Outage behavior stays closed even without configured rate policies.
            return {"allowed": True, "retry_after": 0, "limits": []}
        result = json.loads(client.eval(SCRIPT, len(keys), *keys, json.dumps(specs)))
        # Lua encodes an empty table as {}, normalize the public schema.
        result["limits"] = result["limits"] or []
        return result
    except (redis.RedisError, ValueError, TypeError) as exc:
        raise DependencyUnavailableError(
            code="enforcement_unavailable", message="Access enforcement is temporarily unavailable."
        ) from exc
