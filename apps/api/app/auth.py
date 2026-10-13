"""Supabase JWT verification via the project's JWKS (asymmetric signing keys)."""

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

import jwt
import structlog
from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.errors import Unauthorized

_ALGORITHMS = ["ES256", "RS256", "EdDSA"]
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str | None
    claims: dict[str, Any]


def _jwks(url: str) -> jwt.PyJWKClient:
    if url not in _jwks_clients:
        _jwks_clients[url] = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwks_clients[url]


def decode_token(token: str, settings: Settings, key: Any = None) -> dict[str, Any]:
    """Verify signature, exp and aud. `key` lets tests inject a public key instead of JWKS."""
    try:
        signing_key = key
        if signing_key is None:
            signing_key = _jwks(settings.jwks_url).get_signing_key_from_jwt(token).key
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key,
            algorithms=_ALGORITHMS,
            audience=settings.supabase_jwt_audience,
            options={"require": ["exp", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise Unauthorized("Your session is invalid or expired. Sign in again.") from exc
    return claims


async def current_user(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> CurrentUser:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized()
    claims = decode_token(token, settings, getattr(request.app.state, "jwt_test_key", None))
    try:
        user_id = UUID(str(claims["sub"]))
    except ValueError as exc:
        raise Unauthorized() from exc
    structlog.contextvars.bind_contextvars(user_id=str(user_id))
    return CurrentUser(id=user_id, email=claims.get("email"), claims=claims)


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
