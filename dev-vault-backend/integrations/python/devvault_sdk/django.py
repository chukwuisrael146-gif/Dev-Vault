"""Django view decorator; caller still owns record authorization and business idempotency."""

from functools import wraps
from uuid import uuid4

from django.http import JsonResponse

from devvault_sdk import AccessDenied, VerificationUnavailable


def require_devvault(client, *, scopes, units=1):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return JsonResponse({"error": "invalid_key"}, status=401)
            # Never reuse an untrusted consumer-supplied request ID for fresh work.
            # This decorator makes no automatic retry. Advanced integrations should
            # persist a server-owned operation ID alongside their business result.
            operation_id = str(uuid4())
            try:
                request.devvault = client.verify(
                    api_key=header[7:],
                    required_scopes=list(scopes),
                    request_id=operation_id,
                    units=units,
                    method=request.method,
                )
            except AccessDenied as exc:
                response = JsonResponse({"error": exc.code}, status=exc.status)
                if exc.retry_after:
                    response["Retry-After"] = str(exc.retry_after)
                return response
            except VerificationUnavailable:
                return JsonResponse({"error": "authorization_unavailable"}, status=503)
            return view(request, *args, **kwargs)

        return wrapped

    return decorate
