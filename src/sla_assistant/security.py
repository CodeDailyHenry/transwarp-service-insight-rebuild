from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sla_assistant.identity import Identity, User

bearer = HTTPBearer(auto_error=False)


def get_identity(request: Request) -> Identity:
    return cast(Identity, request.app.state.identity)


def current_user(
    identity: Annotated[Identity, Depends(get_identity)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        identity.record_event("auth.failed")
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    return identity.authenticate(credentials.credentials)


def require_permission(permission: str) -> Callable[..., User]:
    def authorize(
        user: Annotated[User, Depends(current_user)],
        identity: Annotated[Identity, Depends(get_identity)],
    ) -> User:
        identity.authorize(user, permission)
        return user

    return authorize
