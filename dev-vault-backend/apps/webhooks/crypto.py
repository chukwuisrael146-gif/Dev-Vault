import hashlib
import hmac

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


def cipher():
    return MultiFernet([Fernet(value) for value in settings.WEBHOOK_ENCRYPTION_KEYS])


def signature(*, secret, timestamp, body):
    value = str(timestamp).encode("ascii") + b"." + body
    return (
        f"t={timestamp},v1=" + hmac.new(secret.encode("ascii"), value, hashlib.sha256).hexdigest()
    )
