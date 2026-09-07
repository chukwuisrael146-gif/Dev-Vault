"""Dashboard JWT codec. Verification links and API-consumer keys are separate."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

import jwt
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.accounts.exceptions import InvalidSessionTokenError
from apps.accounts.models import RefreshTokenSession, User

TOKEN_MAX_LENGTH = 4096
TokenKind = Literal["access", "refresh"]


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    session_id: UUID
    token_id: UUID
    expires_at: int


@dataclass(frozen=True)
class TokenPair:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_in: int
    refresh_expires_in: int


def credential_hash(user: User) -> str:
    value = f"{user.password}|{user.email}|{user.email_verified_at}"
    return salted_hmac(
        "devvault.dashboard-session.v1",
        value,
        secret=settings.ACCOUNT_JWT_SIGNING_KEY,
        algorithm="sha256",
    ).hexdigest()


def issue_token_pair(*, session: RefreshTokenSession, now: datetime | None = None) -> TokenPair:
    issued_at = int((now or timezone.now()).timestamp())
    refresh_expiry = int(session.expires_at.timestamp())
    access_expiry = min(issued_at + settings.ACCOUNT_ACCESS_TOKEN_SECONDS, refresh_expiry)
    if access_expiry <= issued_at:
        raise InvalidSessionTokenError()
    common = {
        "iss": settings.ACCOUNT_JWT_ISSUER,
        "aud": settings.ACCOUNT_JWT_AUDIENCE,
        "sub": str(session.user_id),
        "sid": str(session.id),
        "iat": issued_at,
        "nbf": issued_at,
    }

    def encode(kind: TokenKind, token_id: UUID, expiry: int) -> str:
        return jwt.encode(
            {**common, "token_type": kind, "jti": str(token_id), "exp": expiry},
            settings.ACCOUNT_JWT_SIGNING_KEY,
            algorithm="HS256",
        )

    return TokenPair(
        access_token=encode("access", uuid4(), access_expiry),
        refresh_token=encode("refresh", session.token_jti, refresh_expiry),
        expires_in=access_expiry - issued_at,
        refresh_expires_in=refresh_expiry - issued_at,
    )


def decode_session_token(*, token: str, kind: TokenKind) -> TokenClaims:
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= TOKEN_MAX_LENGTH:
            raise ValueError
        payload = jwt.decode(
            token,
            settings.ACCOUNT_JWT_SIGNING_KEY,
            algorithms=["HS256"],
            issuer=settings.ACCOUNT_JWT_ISSUER,
            audience=settings.ACCOUNT_JWT_AUDIENCE,
            options={
                "require": ["iss", "aud", "sub", "sid", "jti", "iat", "nbf", "exp", "token_type"],
                "strict_aud": True,
            },
        )
        if payload["token_type"] != kind:
            raise ValueError
        if any(type(payload[key]) is not int for key in ("iat", "nbf", "exp")):
            raise ValueError
        max_lifetime = (
            settings.ACCOUNT_ACCESS_TOKEN_SECONDS
            if kind == "access"
            else settings.ACCOUNT_REFRESH_TOKEN_SECONDS
        )
        if (
            payload["nbf"] != payload["iat"]
            or not 0 < payload["exp"] - payload["iat"] <= max_lifetime
        ):
            raise ValueError
        for key in ("sub", "sid", "jti"):
            if not isinstance(payload[key], str) or str(UUID(payload[key])) != payload[key]:
                raise ValueError
        return TokenClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
            token_id=UUID(payload["jti"]),
            expires_at=payload["exp"],
        )
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise InvalidSessionTokenError() from exc
