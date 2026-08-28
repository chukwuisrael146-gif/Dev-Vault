from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.views import APIView

from api.v1.accounts.serializers import (
    RegistrationSerializer,
    UserSummarySerializer,
)

class RegistrationView(APIView):
    """ Create a new DevVault account."""
    
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        input_serializer = RegistrationSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        
        user = input_serializer.save()
        output_serializer = UserSummarySerializer(user)
        
        return Response(
            {
                "data": {
                    "user": output_serializer.data,
                },
                "message": (
                    "Account created successfully."
                    "Email verification is required."
                ),
            },
            status=status.HTTP_201_CREATED,
        )