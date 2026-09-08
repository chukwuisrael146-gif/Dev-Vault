from django.urls import path

from api.v1.organizations import views

urlpatterns = [
    path("organizations/", views.OrganizationsView.as_view()),
    path("organizations/<uuid:organization_id>/", views.OrganizationView.as_view()),
    path("organizations/<uuid:organization_id>/archive/", views.ArchiveView.as_view()),
    path("organizations/<uuid:organization_id>/members/", views.MembersView.as_view()),
    path(
        "organizations/<uuid:organization_id>/members/<uuid:membership_id>/",
        views.MemberRoleView.as_view(),
    ),
    path(
        "organizations/<uuid:organization_id>/members/<uuid:membership_id>/remove/",
        views.MemberRemoveView.as_view(),
    ),
    path("organizations/<uuid:organization_id>/transfer-ownership/", views.TransferView.as_view()),
    path("organizations/<uuid:organization_id>/invitations/", views.InvitationsView.as_view()),
    path(
        "organizations/<uuid:organization_id>/invitations/<uuid:invitation_id>/revoke/",
        views.InvitationRevokeView.as_view(),
    ),
    path("invitations/accept/", views.InvitationAcceptView.as_view()),
]
