from django.urls import path

from api.v1.access import views
from api.v1.access.verification import VerificationView

urlpatterns = [
    path("access/verify/", VerificationView.as_view()),
    path("services/<uuid:service_id>/permissions/", views.PermissionsView.as_view()),
    path(
        "services/<uuid:service_id>/permissions/<uuid:permission_id>/impact/",
        views.PermissionImpactView.as_view(),
    ),
    path(
        "services/<uuid:service_id>/permissions/<uuid:permission_id>/status/",
        views.PermissionStatusView.as_view(),
    ),
    path("keys/<uuid:key_id>/permissions/", views.KeyPermissionsView.as_view()),
    path("organizations/<uuid:organization_id>/policies/", views.PoliciesView.as_view()),
    path("services/<uuid:service_id>/rate-limit-policies/", views.RatePoliciesView.as_view()),
    path("services/<uuid:service_id>/quota-policies/", views.QuotaPoliciesView.as_view()),
    path("policies/<uuid:policy_id>/", views.PolicyView.as_view()),
    path("policies/<uuid:policy_id>/revisions/", views.PolicyRevisionsView.as_view()),
    path("policies/<uuid:policy_id>/quota-adjustments/", views.QuotaAdjustmentView.as_view()),
]
