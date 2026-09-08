import re

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.profile_services import require_recent_login
from apps.audit.services import record_event
from apps.core.exceptions import ConflictError, DomainError
from apps.core.idempotency import creation_command, remember_created
from apps.organizations.permissions import require_capability
from apps.organizations.selectors import active_organization
from apps.projects.models import APIService, Environment, Project
from apps.projects.selectors import get_environment, get_project, get_service


def _validate_name_slug(name, slug):
    if (
        not name.strip()
        or len(name) > 128
        or len(slug) > 64
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
    ):
        raise DomainError(
            code="validation_error", message="Supply a name and a lowercase URL-safe slug."
        )


@transaction.atomic
def create_project(*, actor, organization_id, name, slug, idempotency_key):
    organization, _ = active_organization(
        actor=actor, organization_id=organization_id, capability="project", lock=True
    )
    _validate_name_slug(name, slug)
    with creation_command(
        actor_id=actor.id,
        scope=f"project:create:{organization.id}",
        key=idempotency_key,
        values={"name": name, "slug": slug},
    ) as command:
        if command.resource_id:
            return get_project(actor=actor, project_id=command.resource_id)[0], False
        try:
            with transaction.atomic():
                project = Project.objects.create(
                    organization=organization, created_by=actor, name=name.strip(), slug=slug
                )
        except IntegrityError as exc:
            raise ConflictError(
                message="This project slug is already in use in the organization."
            ) from exc
        Environment.objects.bulk_create(
            [Environment(project=project, kind=kind) for kind in Environment.Kind.values]
        )
        record_event(
            action="project.created",
            actor_id=actor.id,
            target_id=project.id,
            target_type="projects.Project",
            organization_id=organization.id,
        )
        remember_created(command, project.id)
        return project, True


@transaction.atomic
def update_project(*, actor, project_id, name):
    project, _ = get_project(
        actor=actor, project_id=project_id, capability="project", active=True, lock=True
    )
    _validate_name_slug(name, project.slug)
    project.name = name.strip()
    project.save(update_fields=("name", "updated_at"))
    record_event(
        action="project.updated",
        actor_id=actor.id,
        target_id=project.id,
        target_type="projects.Project",
        organization_id=project.organization_id,
    )
    return project


@transaction.atomic
def archive_project(*, actor, session, project_id, confirm):
    require_recent_login(actor=actor, session=session)
    project, member = get_project(
        actor=actor, project_id=project_id, capability="project", lock=True
    )
    require_capability(member.role, "live_key")  # Archiving also disables live resources.
    if confirm is not True:
        raise DomainError(
            code="confirmation_required", message="Explicit confirmation is required."
        )
    if project.archived_at is None:
        project.archived_at = timezone.now()
        project.save(update_fields=("archived_at", "updated_at"))
        record_event(
            action="project.archived",
            actor_id=actor.id,
            target_id=project.id,
            target_type="projects.Project",
            organization_id=project.organization_id,
        )
    return project


@transaction.atomic
def create_service(*, actor, environment_id, name, slug, audience, idempotency_key):
    environment, member = get_environment(
        actor=actor, environment_id=environment_id, capability="project", active=True, lock=True
    )
    if environment.kind == Environment.Kind.LIVE:
        require_capability(member.role, "live_key")
    _validate_name_slug(name, slug)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}", audience):
        raise DomainError(
            code="validation_error",
            message="Supply a stable audience identifier of at most 128 characters.",
        )
    with creation_command(
        actor_id=actor.id,
        scope=f"service:create:{environment.id}",
        key=idempotency_key,
        values={"name": name, "slug": slug, "audience": audience},
    ) as command:
        if command.resource_id:
            return get_service(actor=actor, service_id=command.resource_id)[0], False
        try:
            with transaction.atomic():
                service = APIService.objects.create(
                    environment=environment, name=name.strip(), slug=slug, audience=audience
                )
        except IntegrityError as exc:
            raise ConflictError(
                message="This service slug or audience already exists in the environment."
            ) from exc
        record_event(
            action="service.created",
            actor_id=actor.id,
            target_id=service.id,
            target_type="projects.APIService",
            organization_id=environment.project.organization_id,
        )
        remember_created(command, service.id)
        return service, True


@transaction.atomic
def set_service_status(*, actor, session, service_id, is_active, confirm):
    require_recent_login(actor=actor, session=session)
    service, member = get_service(
        actor=actor, service_id=service_id, capability="project", lock=True
    )
    # Reactivation cannot bypass a disabled parent chain.
    environment, _ = get_environment(
        actor=actor, environment_id=service.environment_id, active=True
    )
    if environment.kind == Environment.Kind.LIVE:
        require_capability(member.role, "live_key")
    if confirm is not True or type(is_active) is not bool:
        raise DomainError(
            code="confirmation_required",
            message="Explicit confirmation and a boolean status are required.",
        )
    if service.is_active != is_active:
        service.is_active = is_active
        service.save(update_fields=("is_active", "updated_at"))
        record_event(
            action="service.status_changed",
            actor_id=actor.id,
            target_id=service.id,
            target_type="projects.APIService",
            organization_id=environment.project.organization_id,
            changes={"is_active": is_active},
        )
    return service
