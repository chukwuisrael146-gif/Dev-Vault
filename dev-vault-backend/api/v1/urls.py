from django.urls import path, include

urlpatterns = [
    path('auth/', include('api.v1.accounts.urls')),
    path('health/', include('apps.core.urls')),
]