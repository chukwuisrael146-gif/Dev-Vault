from django.urls import path

from api.v1.credentials import views

urlpatterns = [
    path("environments/<uuid:environment_id>/keys/", views.KeysView.as_view()),
    path("keys/<uuid:key_id>/", views.KeyView.as_view()),
    path("keys/<uuid:key_id>/revoke/", views.KeyRevokeView.as_view()),
    path("keys/<uuid:key_id>/rotate/", views.KeyRotateView.as_view()),
    path("services/<uuid:service_id>/integration-credentials/", views.IntegrationsView.as_view()),
    path(
        "services/<uuid:service_id>/integration-credentials/<uuid:credential_id>/revoke/",
        views.IntegrationRevokeView.as_view(),
    ),
]
