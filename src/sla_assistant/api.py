from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from sla_assistant.config import database_url
from sla_assistant.identity import Identity, IdentityError, Role, User
from sla_assistant.security import current_user, get_identity, require_permission

Admin = Annotated[User, Depends(require_permission("manage_users"))]


class CreateUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    role: Role = Role.USER


class UpdateUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role | None = None
    enabled: bool | None = None


def create_app(identity: Identity | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.identity = identity or Identity.open(database_url())
        try:
            yield
        finally:
            if identity is None:
                app.state.identity.close()

    app = FastAPI(title="SLA Intelligent Diagnosis API", lifespan=lifespan)

    @app.exception_handler(IdentityError)
    async def identity_error(request: Request, exc: IdentityError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else {}
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code, headers=headers)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse({"detail": "Identity database is unavailable"}, status_code=503)

    @app.get("/health/live")
    def liveness() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def readiness(store: Annotated[Identity, Depends(get_identity)]) -> dict[str, str]:
        store.check_ready()
        return {"status": "ready"}

    @app.get("/v1/auth/me")
    def me(user: Annotated[User, Depends(current_user)]) -> User:
        return user

    @app.get("/v1/admin/users")
    def list_users(actor: Admin, store: Annotated[Identity, Depends(get_identity)]) -> list[User]:
        return store.list_users()

    @app.post("/v1/admin/users", status_code=201)
    def create_user(
        body: CreateUser, actor: Admin, store: Annotated[Identity, Depends(get_identity)]
    ) -> JSONResponse:
        issued = store.create_user(body.username, body.role, actor_id=actor.id)
        return JSONResponse(asdict(issued), status_code=201, headers={"Cache-Control": "no-store"})

    @app.post("/v1/admin/users/{user_id}/reset-token")
    def reset_token(
        user_id: str, actor: Admin, store: Annotated[Identity, Depends(get_identity)]
    ) -> JSONResponse:
        return JSONResponse(
            asdict(store.reset_token(user_id, actor_id=actor.id)),
            headers={"Cache-Control": "no-store"},
        )

    @app.patch("/v1/admin/users/{user_id}")
    def update_user(
        user_id: str,
        body: UpdateUser,
        actor: Admin,
        store: Annotated[Identity, Depends(get_identity)],
    ) -> User:
        return store.update_user(user_id, body.role, body.enabled, actor_id=actor.id)

    @app.get("/v1/admin/audit")
    def list_audit(
        actor: Admin, store: Annotated[Identity, Depends(get_identity)]
    ) -> list[dict[str, Any]]:
        return store.list_audit()

    return app


app = create_app()
