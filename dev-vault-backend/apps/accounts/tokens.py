from uuid import UUID

from django.core import signing

from apps.accounts.exceptions import InvalidEmailVerificationError
from apps.accounts.models import User

TOKEN_PREFIX = "dv_verify_"


def _signer(user: User) -> signing.Signer:
    # Bind the signature to the current password hash; a password change revokes links.
    return signing.Signer(salt=f"devvault.email-verification.v1:{user.password}")


def make_verification_token(*, verification_id: UUID, user: User) -> str:
    return TOKEN_PREFIX + _signer(user).sign(str(verification_id))


def verification_id_from_token(token: str) -> UUID:
    """Parse an untrusted lookup ID. This alone NEVER authorizes verification."""
    try:
        if not isinstance(token, str) or len(token) > 256 or not token.startswith(TOKEN_PREFIX):
            raise ValueError
        return UUID(token.removeprefix(TOKEN_PREFIX).split(":", 1)[0])
    except (ValueError, AttributeError) as exc:
        raise InvalidEmailVerificationError() from exc


def validate_verification_signature(*, token: str, verification_id: UUID, user: User) -> None:
    try:
        value = _signer(user).unsign(token.removeprefix(TOKEN_PREFIX))
        if value != str(verification_id):
            raise signing.BadSignature
    except signing.BadSignature as exc:
        raise InvalidEmailVerificationError() from exc
