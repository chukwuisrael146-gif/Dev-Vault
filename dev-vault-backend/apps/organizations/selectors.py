from uuid import UUID

from apps.accounts.models import User
from apps.core.exceptions import ForbiddenError, NotFoundError
from apps.organizations.models import Organization, OrganizationMembership
from apps.organizations.permissions import require_capability


def organizations_for(actor: User):
    if not actor.can_authenticate or not actor.email_is_verified:
        raise ForbiddenError()
    return Organization.objects.filter(memberships__user=actor, memberships__is_active=True)


def get_organization(*, actor: User, organization_id: UUID, capability: str = "read", lock=False):
    query = organizations_for(actor)
    if lock:
        query = query.select_for_update(of=("self",))
    organization = query.filter(pk=organization_id).first()
    if organization is None:
        raise NotFoundError()
    member = OrganizationMembership.objects.filter(
        organization=organization,
        user=actor,
        is_active=True,
    ).first()
    if member is None:
        raise NotFoundError()
    require_capability(member.role, capability)
    return organization, member


def active_organization(*, actor: User, organization_id: UUID, capability="read", lock=False):
    organization, member = get_organization(
        actor=actor, organization_id=organization_id, capability=capability, lock=lock
    )
    if organization.status != Organization.Status.ACTIVE:
        raise ForbiddenError(
            code="organization_inactive", message="The organization is not active."
        )
    return organization, member


def memberships_for(*, actor: User, organization_id: UUID):
    organization, _ = get_organization(actor=actor, organization_id=organization_id)
    return OrganizationMembership.objects.filter(
        organization=organization, is_active=True
    ).select_related("user")
