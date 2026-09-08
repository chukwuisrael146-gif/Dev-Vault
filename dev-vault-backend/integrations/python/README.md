# Python / Django SDK

Install locally with `pip install ./integrations/python` (Python 3.11+).
No package was published to a public registry. Use this only in a trusted backend.

```python
import os
from uuid import uuid4
from devvault_sdk import Client, AccessDenied, VerificationUnavailable

client = Client(
    base_url=os.environ["DEVVAULT_URL"],
    service_id=os.environ["DEVVAULT_SERVICE_ID"],
    environment="test",
    audience="orders-api",
    integration_secret=os.environ["DEVVAULT_INTEGRATION_SECRET"],
    allow_insecure_local=False,  # True only for explicit loopback HTTP development
)

decision = client.verify(
    api_key=customer_key,
    required_scopes=["orders:read"],
    request_id=str(uuid4()),  # Server-owned; persist for an exact workflow retry
    method="GET",
    units=1,
)
```

Catch `AccessDenied` and return its safe status/code and optional retry delay.
Catch `VerificationUnavailable` and return 503 without executing protected work.
The client does not automatically retry, redirect, use environment proxies or
cache a fail-open authorization result.

For Django, use `@require_devvault(client, scopes=["orders:read"])` from
`devvault_sdk.django`; a successful decision is available as `request.devvault`.
The decorator creates a fresh server-owned operation ID per request. For durable
business retries use `Client.verify` directly with your own saved operation/result
mapping. Never reuse untrusted consumer IDs to bypass metering for fresh work.
DevVault does not replace your application's record-ownership checks.
