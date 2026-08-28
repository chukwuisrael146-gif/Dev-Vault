from django.urls import path

from api.v1.accounts.views import RegistrationView

app_name = 'accounts'

urlpatterns = [
    path('register/', RegistrationView.as_view(), name='register'),
]
