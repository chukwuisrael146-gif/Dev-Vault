from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.organizations.serializers import (
    ConfirmationInput,
    InvitationAccept,
    InvitationInput,
    InvitationOutput,
    MemberOutput,
    OrganizationInput,
    OrganizationOutput,
    OrganizationUpdate,
    RoleInput,
    TransferInput,
)
from apps.core.pagination import DefaultCursorPagination
from apps.organizations import selectors, services


def validated(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def paginated(queryset, serializer_class, request):
    paginator = DefaultCursorPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(serializer_class(page, many=True).data)


class OrganizationsView(APIView):
    def get(self, request):
        return paginated(selectors.organizations_for(request.user), OrganizationOutput, request)

    def post(self, request):
        organization, created = services.create_organization(
            actor=request.user,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **validated(OrganizationInput, request),
        )
        return Response(
            {"data": OrganizationOutput(organization).data}, status=201 if created else 200
        )


class OrganizationView(APIView):
    def get(self, request, organization_id):
        organization, _ = selectors.get_organization(
            actor=request.user, organization_id=organization_id
        )
        return Response({"data": OrganizationOutput(organization).data})

    def patch(self, request, organization_id):
        organization = services.update_organization(
            actor=request.user,
            organization_id=organization_id,
            **validated(OrganizationUpdate, request),
        )
        return Response({"data": OrganizationOutput(organization).data})


class ArchiveView(APIView):
    def post(self, request, organization_id):
        organization = services.archive_organization(
            actor=request.user,
            session=request.auth,
            organization_id=organization_id,
            **validated(ConfirmationInput, request),
        )
        return Response({"data": OrganizationOutput(organization).data})


class MembersView(APIView):
    def get(self, request, organization_id):
        return paginated(
            selectors.memberships_for(actor=request.user, organization_id=organization_id),
            MemberOutput,
            request,
        )


class MemberRoleView(APIView):
    def patch(self, request, organization_id, membership_id):
        member = services.change_member_role(
            actor=request.user,
            session=request.auth,
            organization_id=organization_id,
            membership_id=membership_id,
            **validated(RoleInput, request),
        )
        return Response({"data": MemberOutput(member).data})


class MemberRemoveView(APIView):
    def post(self, request, organization_id, membership_id):
        services.remove_member(
            actor=request.user,
            session=request.auth,
            organization_id=organization_id,
            membership_id=membership_id,
            **validated(ConfirmationInput, request),
        )
        return Response(status=204)


class TransferView(APIView):
    def post(self, request, organization_id):
        services.transfer_ownership(
            actor=request.user,
            session=request.auth,
            organization_id=organization_id,
            **validated(TransferInput, request),
        )
        return Response(status=204)


class InvitationsView(APIView):
    def get(self, request, organization_id):
        organization, _ = selectors.get_organization(
            actor=request.user, organization_id=organization_id, capability="team"
        )
        from apps.organizations.models import OrganizationInvitation

        return paginated(
            OrganizationInvitation.objects.filter(organization=organization),
            InvitationOutput,
            request,
        )

    def post(self, request, organization_id):
        invitation = services.invite_member(
            actor=request.user,
            organization_id=organization_id,
            **validated(InvitationInput, request),
        )
        return Response({"data": InvitationOutput(invitation).data}, status=201)


class InvitationRevokeView(APIView):
    def post(self, request, organization_id, invitation_id):
        services.revoke_invitation(
            actor=request.user, organization_id=organization_id, invitation_id=invitation_id
        )
        return Response(status=204)


class InvitationAcceptView(APIView):
    def post(self, request):
        member = services.accept_invitation(
            actor=request.user, **validated(InvitationAccept, request)
        )
        return Response({"data": MemberOutput(member).data})
