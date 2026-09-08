from django.urls import path

from api.v1.projects import views

urlpatterns = [
    path("organizations/<uuid:organization_id>/projects/", views.ProjectsView.as_view()),
    path("projects/<uuid:project_id>/", views.ProjectView.as_view()),
    path("projects/<uuid:project_id>/archive/", views.ProjectArchiveView.as_view()),
    path("projects/<uuid:project_id>/environments/", views.EnvironmentsView.as_view()),
    path("environments/<uuid:environment_id>/services/", views.ServicesView.as_view()),
    path("services/<uuid:service_id>/", views.ServiceView.as_view()),
    path("services/<uuid:service_id>/status/", views.ServiceStatusView.as_view()),
]
