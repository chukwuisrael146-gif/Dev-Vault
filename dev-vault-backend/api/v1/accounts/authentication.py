from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.auth_services import authenticate_access_token
from apps.accounts.exceptions import InvalidSessionTokenError


class InvalidAccessToken(AuthenticationFailed):
    default_detail = "The token is invalid or expired. Please sign in again."
    default_code = "invalid_token"


class DashboardJWTAuthentication(BaseAuthentication):
    """Accept only Bearer access JWTs backed by a currently valid dashboard session."""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            raise InvalidAccessToken()
        try:
            token = parts[1].decode("ascii")
            return authenticate_access_token(access_token=token)
        except (UnicodeDecodeError, InvalidSessionTokenError) as exc:
            raise InvalidAccessToken() from exc

    def authenticate_header(self, request):
        return 'Bearer realm="devvault"'
