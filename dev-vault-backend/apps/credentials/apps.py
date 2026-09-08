from django.apps import AppConfig


class CredentialsConfig(AppConfig):
    name = "apps.credentials"

    def ready(self):
        from apps.credentials import checks  # noqa: F401
