"""Tenant lifecycle and membership commands. Mutations serialize on the tenant row."""

import logging
import re
import secrets
from datetime import timedelta
from smtplib import SMTPException
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.managers import UserManager
from apps.accounts.models import User
from apps.accounts.profile_services import require_recent_login
from apps.audit.services import record_event
from apps.core.exceptions import ConflictError, DomainError, ForbiddenError, NotFoundError
from apps.core.idempotency import creation_command, remember_created
from apps.organizations.models import Organization, OrganizationInvitation, OrganizationMembership
from apps.organizations.permissions import require_capability
from apps.organizations.selectors import active_organization, get_organization, organizations_for

logger = logging.getLogger(__name__)
Role = OrganizationMembership.Role


def _audit(action, organization, actor, target, target_type, changes=None):
    record_event(
        action=action,
        organization_id=organization.id,
        actor_id=actor.id if actor else None,
        target_id=target.id,
        target_type=target_type,
        changes=changes,
    )


def create_organization(*, actor: User, name: str, slug: str, idempotency_key: str):
    organizations_for(actor)  # Account eligibility is enforced for direct service callers too.
    if (
        not name.strip()
        or len(name) > 128
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
        or len(slug) > 64
    ):
        raise DomainError(
            code="validation_error", message="Supply a name and a lowercase URL-safe slug."
        )
    with creation_command(
        actor_id=actor.id,
        scope="organization:create",
        key=idempotency_key,
        values={"name": name, "slug": slug},
    ) as command:
        if command.resource_id:
            return get_organization(actor=actor, organization_id=command.resource_id)[0], False
        try:
            with transaction.atomic():
                organization = Organization.objects.create(name=name.strip(), slug=slug)
        except IntegrityError as exc:
            raise ConflictError(message="This organization slug is unavailable.") from exc
        OrganizationMembership.objects.create(
            organization=organization, user=actor, role=Role.OWNER
        )
        _audit(
            "organization.created", organization, actor, organization, "organizations.Organization"
        )
        remember_created(command, organization.id)
        return organization, True


@transaction.atomic
def update_organization(*, actor, organization_id, name):
    organization, _ = active_organization(
        actor=actor, organization_id=organization_id, capability="organization", lock=True
    )
    if not name.strip() or len(name) > 128:
        raise DomainError(code="validation_error", message="Name must be 1–128 characters.")
    organization.name = name.strip()
    organization.save(update_fields=("name", "updated_at"))
    _audit("organization.updated", organization, actor, organization, "organizations.Organization")
    return organization


@transaction.atomic
def archive_organization(*, actor, session, organization_id, confirm):
    require_recent_login(actor=actor, session=session)
    organization, _ = get_organization(
        actor=actor, organization_id=organization_id, capability="organization", lock=True
    )
    if confirm is not True:
        raise DomainError(
            code="confirmation_required", message="Explicit confirmation is required."
        )
    if organization.status != Organization.Status.ARCHIVED:
        organization.status = Organization.Status.ARCHIVED
        organization.save(update_fields=("status", "updated_at"))
        _audit(
            "organization.archived", organization, actor, organization, "organizations.Organization"
        )
    return organization


def _check_role_change(actor_member, target_role, existing_role=None):
    if target_role not in Role.values:
        raise DomainError(code="validation_error", message="Unknown organization role.")
    if (
        target_role in {Role.OWNER, Role.ADMIN} or existing_role in {Role.OWNER, Role.ADMIN}
    ) and actor_member.role != Role.OWNER:
        raise ForbiddenError()


@transaction.atomic
def change_member_role(*, actor, session, organization_id, membership_id, role):
    require_recent_login(actor=actor, session=session)
    organization, acting = active_organization(
        actor=actor, organization_id=organization_id, capability="team", lock=True
    )
    member = OrganizationMembership.objects.filter(
        pk=membership_id, organization=organization, is_active=True
    ).first()
    if member is None:
        raise NotFoundError()
    _check_role_change(acting, role, member.role)
    if (
        member.role == Role.OWNER
        and role != Role.OWNER
        and OrganizationMembership.objects.filter(
            organization=organization,
            role=Role.OWNER,
            is_active=True,
            user__is_active=True,
            user__status=User.Status.ACTIVE,
            user__email_verified_at__isnull=False,
        ).count()
        <= 1
    ):
        raise ConflictError(code="last_owner", message="The organization must retain an owner.")
    before = member.role
    member.role = role
    member.save(update_fields=("role", "updated_at"))
    _audit(
        "organization.member_role_changed",
        organization,
        actor,
        member,
        "organizations.OrganizationMembership",
        {"previous_role": before, "role": role},
    )
    return member


@transaction.atomic
def remove_member(*, actor, session, organization_id, membership_id, confirm):
    require_recent_login(actor=actor, session=session)
    organization, acting = active_organization(
        actor=actor, organization_id=organization_id, capability="team", lock=True
    )
    member = OrganizationMembership.objects.filter(
        pk=membership_id, organization=organization, is_active=True
    ).first()
    if member is None:
        raise NotFoundError()
    if confirm is not True:
        raise DomainError(
            code="confirmation_required", message="Explicit confirmation is required."
        )
    _check_role_change(acting, Role.DEVELOPER, member.role)
    if (
        member.role == Role.OWNER
        and OrganizationMembership.objects.filter(
            organization=organization,
            role=Role.OWNER,
            is_active=True,
            user__is_active=True,
            user__status=User.Status.ACTIVE,
            user__email_verified_at__isnull=False,
        ).count()
        <= 1
    ):
        raise ConflictError(code="last_owner", message="The organization must retain an owner.")
    member.is_active = False
    member.save(update_fields=("is_active", "updated_at"))
    _audit(
        "organization.member_removed",
        organization,
        actor,
        member,
        "organizations.OrganizationMembership",
    )


@transaction.atomic
def transfer_ownership(*, actor, session, organization_id, membership_id, confirm):
    require_recent_login(actor=actor, session=session)
    organization, acting = active_organization(
        actor=actor, organization_id=organization_id, capability="ownership", lock=True
    )
    target = OrganizationMembership.objects.filter(
        pk=membership_id,
        organization=organization,
        is_active=True,
        user__is_active=True,
        user__status=User.Status.ACTIVE,
        user__email_verified_at__isnull=False,
    ).first()
    if target is None:
        raise NotFoundError()
    if confirm is not True or target.user_id == actor.id:
        raise DomainError(
            code="confirmation_required", message="Confirm transfer to another active member."
        )
    target.role = Role.OWNER
    target.save(update_fields=("role", "updated_at"))
    acting.role = Role.ADMIN
    acting.save(update_fields=("role", "updated_at"))
    _audit(
        "organization.ownership_transferred",
        organization,
        actor,
        target,
        "organizations.OrganizationMembership",
    )


@transaction.atomic
def invite_member(*, actor, organization_id, email, role):
    organization, acting = active_organization(
        actor=actor, organization_id=organization_id, capability="team", lock=True
    )
    _check_role_change(acting, role)
    if role == Role.OWNER:
        raise DomainError(
            code="validation_error", message="Invite a member first, then transfer ownership."
        )
    email = UserManager.normalize_email_address(email)
    if OrganizationMembership.objects.filter(
        organization=organization, user__email=email, is_active=True
    ).exists():
        raise ConflictError(message="This account is already an active member.")
    now = timezone.now()
    open_requests = OrganizationInvitation.objects.filter(
        organization=organization, email=email, accepted_at__isnull=True, revoked_at__isnull=True
    )
    if open_requests.filter(created_at__gt=now - timedelta(seconds=60)).exists():
        raise ConflictError(
            code="invitation_cooldown", message="Wait a minute before sending another invitation."
        )
    open_requests.update(revoked_at=now, updated_at=now)
    invitation = OrganizationInvitation.objects.create(
        organization=organization,
        email=email,
        role=role,
        invited_by=actor,
        expires_at=now + timedelta(days=7),
        next_attempt_at=now,
    )
    _audit(
        "organization.member_invited",
        organization,
        actor,
        invitation,
        "organizations.OrganizationInvitation",
        {"role": role},
    )
    return invitation


def _invitation_signer(invitation):
    return signing.Signer(
        salt=f"devvault.invitation.v1:{invitation.organization_id}:{invitation.email}:{invitation.role}"
    )


def invitation_token(invitation):
    return "dv_invite_" + _invitation_signer(invitation).sign(str(invitation.id))


@transaction.atomic
def accept_invitation(*, actor, token):
    organizations_for(actor)
    try:
        if not isinstance(token, str) or not token.startswith("dv_invite_") or len(token) > 256:
            raise ValueError
        identifier = UUID(token.removeprefix("dv_invite_").split(":", 1)[0])
    except ValueError as exc:
        raise DomainError(
            code="invalid_invitation", message="The invitation is invalid or expired."
        ) from exc
    # Email ownership is required before loading a tenant through an invitation.
    candidate = OrganizationInvitation.objects.filter(pk=identifier, email=actor.email).first()
    if candidate is None:
        raise DomainError(
            code="invalid_invitation", message="The invitation is invalid or expired."
        )
    organization = Organization.objects.select_for_update().get(pk=candidate.organization_id)
    invitation = OrganizationInvitation.objects.select_for_update().get(pk=candidate.id)
    inviter = OrganizationMembership.objects.filter(
        organization=organization,
        user=invitation.invited_by,
        is_active=True,
        user__is_active=True,
        user__status=User.Status.ACTIVE,
        user__email_verified_at__isnull=False,
    ).first()
    if inviter is None:
        raise DomainError(
            code="invalid_invitation", message="The invitation is invalid or expired."
        )
    try:
        require_capability(inviter.role, "team")
        _check_role_change(inviter, invitation.role)
    except ForbiddenError as exc:
        raise DomainError(
            code="invalid_invitation", message="The invitation is invalid or expired."
        ) from exc
    try:
        value = _invitation_signer(invitation).unsign(token.removeprefix("dv_invite_"))
        if value != str(invitation.id):
            raise signing.BadSignature
    except signing.BadSignature as exc:
        raise DomainError(
            code="invalid_invitation", message="The invitation is invalid or expired."
        ) from exc
    if (
        invitation.accepted_at
        or invitation.revoked_at
        or invitation.expires_at <= timezone.now()
        or organization.status != Organization.Status.ACTIVE
    ):
        raise DomainError(
            code="invalid_invitation", message="The invitation is invalid or expired."
        )
    membership = OrganizationMembership.objects.filter(
        organization=organization, user=actor
    ).first()
    if membership and membership.is_active:
        raise ConflictError(message="You are already an active member.")
    if membership:
        membership.role, membership.is_active = invitation.role, True
        membership.save(update_fields=("role", "is_active", "updated_at"))
    else:
        membership = OrganizationMembership.objects.create(
            organization=organization, user=actor, role=invitation.role
        )
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=("accepted_at", "updated_at"))
    _audit(
        "organization.member_joined",
        organization,
        actor,
        membership,
        "organizations.OrganizationMembership",
    )
    return membership


@transaction.atomic
def revoke_invitation(*, actor, organization_id, invitation_id):
    organization, _ = active_organization(
        actor=actor, organization_id=organization_id, capability="team", lock=True
    )
    invitation = OrganizationInvitation.objects.filter(
        pk=invitation_id, organization=organization
    ).first()
    if invitation is None:
        raise NotFoundError()
    if invitation.accepted_at:
        raise ConflictError(message="The invitation has already been accepted.")
    if not invitation.revoked_at:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=("revoked_at", "updated_at"))
        _audit(
            "organization.invitation_revoked",
            organization,
            actor,
            invitation,
            "organizations.OrganizationInvitation",
        )


@transaction.atomic
def deliver_invitation(*, identifier):
    candidate = OrganizationInvitation.objects.filter(pk=identifier).first()
    if candidate is None:
        return False
    organization = Organization.objects.select_for_update().get(pk=candidate.organization_id)
    row = OrganizationInvitation.objects.select_for_update().get(pk=identifier)
    now = timezone.now()
    if (
        row.sent_at
        or row.accepted_at
        or row.revoked_at
        or row.expires_at <= now
        or row.next_attempt_at > now
        or row.attempts >= 5
        or organization.status != Organization.Status.ACTIVE
    ):
        return False
    row.attempts += 1
    try:
        # Token is only in the intended email; no response/task/audit receives it.
        accepted = EmailMessage(
            subject="You are invited to a DevVault organization",
            body=f"You have been invited to {organization.name} as {row.role}.\n"
            "Sign in with this verified email address and accept using this invitation token:\n\n"
            f"{invitation_token(row)}\n\nExpires at {row.expires_at.isoformat()} (UTC).\n",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[row.email],
        ).send(using="default")
        if accepted != 1:
            raise OSError("Email was not accepted")
    except (OSError, SMTPException) as exc:
        row.next_attempt_at = now + timedelta(seconds=30 * 2**row.attempts + secrets.randbelow(30))
        logger.warning("Invitation email delivery failed", extra={"error_type": type(exc).__name__})
    else:
        row.sent_at = timezone.now()
    row.save(update_fields=("sent_at", "attempts", "next_attempt_at", "updated_at"))
    return row.sent_at is not None


def deliver_pending_invitations():
    now = timezone.now()
    identifiers = list(
        OrganizationInvitation.objects.filter(
            sent_at__isnull=True,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
            next_attempt_at__lte=now,
            attempts__lt=5,
        )
        .order_by("next_attempt_at", "id")
        .values_list("id", flat=True)[:25]
    )
    return sum(deliver_invitation(identifier=identifier) for identifier in identifiers)
