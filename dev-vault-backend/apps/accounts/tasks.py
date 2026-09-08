from celery import shared_task

from apps.accounts.profile_services import deliver_pending_password_resets
from apps.accounts.services import deliver_pending_verification_emails


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=330)
def deliver_pending_verifications() -> int:
    return deliver_pending_verification_emails()


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=330)
def deliver_pending_resets() -> int:
    return deliver_pending_password_resets()
