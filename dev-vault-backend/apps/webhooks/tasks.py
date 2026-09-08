from celery import shared_task

from apps.webhooks.services import deliver_pending


@shared_task(ignore_result=True)
def deliver_webhooks():
    return deliver_pending()
