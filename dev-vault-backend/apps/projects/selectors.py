from apps.core.exceptions import ForbiddenError, NotFoundError
from apps.organizations.selectors import active_organization, get_organization, organizations_for
from apps.projects.models import APIService, Environment, Project


def projects_for(*, actor, organization_id):
    organization, _ = get_organization(actor=actor, organization_id=organization_id)
    return Project.objects.filter(organization=organization)


def get_project(*, actor, project_id, capability="read", active=False, lock=False):
    project = Project.objects.filter(
        organization__in=organizations_for(actor), pk=project_id
    ).first()
    if project is None:
        raise NotFoundError()
    guard = active_organization if active else get_organization
    _, member = guard(
        actor=actor, organization_id=project.organization_id, capability=capability, lock=lock
    )
    if lock:
        project = Project.objects.select_for_update().get(pk=project.id)
    if active and project.archived_at:
        raise ForbiddenError(code="project_archived", message="This project is archived.")
    return project, member


def environments_for(*, actor, project_id):
    project, _ = get_project(actor=actor, project_id=project_id)
    return Environment.objects.filter(project=project)


def get_environment(*, actor, environment_id, capability="read", active=False, lock=False):
    environment = Environment.objects.filter(
        project__organization__in=organizations_for(actor), pk=environment_id
    ).first()
    if environment is None:
        raise NotFoundError()
    _, member = get_project(
        actor=actor,
        project_id=environment.project_id,
        capability=capability,
        active=active,
        lock=lock,
    )
    if lock:
        environment = Environment.objects.select_for_update().get(pk=environment.id)
    if active and not environment.is_active:
        raise ForbiddenError(code="environment_inactive", message="This environment is not active.")
    return environment, member


def services_for(*, actor, environment_id):
    environment, _ = get_environment(actor=actor, environment_id=environment_id)
    return APIService.objects.filter(environment=environment)


def get_service(*, actor, service_id, capability="read", active=False, lock=False):
    service = APIService.objects.filter(
        environment__project__organization__in=organizations_for(actor), pk=service_id
    ).first()
    if service is None:
        raise NotFoundError()
    _, member = get_environment(
        actor=actor,
        environment_id=service.environment_id,
        capability=capability,
        active=active,
        lock=lock,
    )
    if lock:
        service = APIService.objects.select_for_update().get(pk=service.id)
    if active and not service.is_active:
        raise ForbiddenError(code="service_inactive", message="This API service is not active.")
    return service, member
