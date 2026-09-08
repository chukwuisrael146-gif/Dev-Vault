from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, register


@register()
def webhook_key_checks(app_configs, **kwargs):
    keys = settings.WEBHOOK_ENCRYPTION_KEYS
    try:
        if not isinstance(keys, list) or not 1 <= len(keys) <= 5:
            raise ValueError
        for value in keys:
            Fernet(value)
    except TypeError, ValueError:
        return [
            Error(
                "Configure 1–5 valid Fernet encryption keys for webhook secrets.",
                id="webhooks.E001",
            )
        ]
    return []
