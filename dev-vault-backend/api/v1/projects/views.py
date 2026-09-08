from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.helpers import paginated, validated
from api.v1.organizations.serializers import ConfirmationInput
from api.v1.projects.serializers import (
    EnvironmentOutput,
    ProjectInput,
    ProjectOutput,
    ProjectUpdate,
    ServiceInput,
    ServiceOutput,
    ServiceStatusInput,
)
from apps.projects import selectors, services


class ProjectsView(APIView):
    def get(self, request, organization_id):
        return paginated(
            selectors.projects_for(actor=request.user, organization_id=organization_id),
            ProjectOutput,
            request,
        )

    def post(self, request, organization_id):
        project, created = services.create_project(
            actor=request.user,
            organization_id=organization_id,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(ProjectInput, request),
        )
        return Response({"data": ProjectOutput(project).data}, status=201 if created else 200)


class ProjectView(APIView):
    def get(self, request, project_id):
        project, _ = selectors.get_project(actor=request.user, project_id=project_id)
        return Response({"data": ProjectOutput(project).data})

    def patch(self, request, project_id):
        project = services.update_project(
            actor=request.user, project_id=project_id, **validated(ProjectUpdate, request)
        )
        return Response({"data": ProjectOutput(project).data})


class ProjectArchiveView(APIView):
    def post(self, request, project_id):
        project = services.archive_project(
            actor=request.user,
            session=request.auth,
            project_id=project_id,
            **validated(ConfirmationInput, request),
        )
        return Response({"data": ProjectOutput(project).data})


class EnvironmentsView(APIView):
    def get(self, request, project_id):
        return Response(
            {
                "data": EnvironmentOutput(
                    selectors.environments_for(actor=request.user, project_id=project_id), many=True
                ).data
            }
        )


class ServicesView(APIView):
    def get(self, request, environment_id):
        return paginated(
            selectors.services_for(actor=request.user, environment_id=environment_id),
            ServiceOutput,
            request,
        )

    def post(self, request, environment_id):
        service, created = services.create_service(
            actor=request.user,
            environment_id=environment_id,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(ServiceInput, request),
        )
        return Response({"data": ServiceOutput(service).data}, status=201 if created else 200)


class ServiceView(APIView):
    def get(self, request, service_id):
        service, _ = selectors.get_service(actor=request.user, service_id=service_id)
        return Response({"data": ServiceOutput(service).data})


class ServiceStatusView(APIView):
    def post(self, request, service_id):
        service = services.set_service_status(
            actor=request.user,
            session=request.auth,
            service_id=service_id,
            **validated(ServiceStatusInput, request),
        )
        return Response({"data": ServiceOutput(service).data})
