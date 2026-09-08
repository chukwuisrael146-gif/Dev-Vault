from celery import shared_task

from apps.usage.exports import process_usage_exports  # noqa: F401
from apps.usage.services import aggregate_pending


@shared_task(ignore_result=True)
def aggregate_usage():
    return aggregate_pending()
