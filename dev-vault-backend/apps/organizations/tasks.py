from celery import shared_task

from apps.organizations.services import deliver_pending_invitations


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=330)
def deliver_invitations():
    return deliver_pending_invitations()
