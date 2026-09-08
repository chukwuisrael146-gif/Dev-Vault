from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    name = "apps.webhooks"

    def ready(self):
        from apps.webhooks import checks, receivers  # noqa: F401
