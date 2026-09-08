import re

from django.conf import settings
from django.core.checks import Error, register


@register()
def check_pepper_settings(app_configs, **kwargs):
    peppers = settings.API_KEY_PEPPERS
    if not isinstance(peppers, dict) or settings.API_KEY_ACTIVE_PEPPER_VERSION not in peppers:
        return [Error("Configure the active API key pepper version.", id="credentials.E001")]
    for version, secret in peppers.items():
        if (
            not re.fullmatch(r"[a-zA-Z0-9_.-]{1,16}", version)
            or not isinstance(secret, str)
            or len(secret.encode()) < 32
            or secret in {settings.SECRET_KEY, settings.ACCOUNT_JWT_SIGNING_KEY}
        ):
            return [
                Error(
                    "API key peppers must be independent secrets of at least 32 bytes "
                    "with valid version labels.",
                    id="credentials.E002",
                )
            ]
    return []
