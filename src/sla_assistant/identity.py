"""Persistent identities. Plaintext personal tokens exist only at issuance boundaries."""

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    URL,
    Boolean,
    Column,
    Connection,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError


class Role(StrEnum):
    USER = "user"
    CURATOR = "curator"
    ADMIN = "admin"


@dataclass(frozen=True)
class User:
    id: str
    username: str
    role: Role
    enabled: bool
    external_identity: str | None


@dataclass(frozen=True)
class IssuedToken:
    user: User
    token: str = field(repr=False)


class IdentityError(Exception):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


metadata = MetaData()
users = Table(
    "identity_users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("role", String(16), nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("external_identity", String(255), nullable=True, unique=True),
    Column("token_hash", String(64), nullable=False, unique=True),
)
bootstrap_guard = Table(
    "identity_bootstrap",
    metadata,
    Column("id", Integer, primary_key=True),
)
audit_events = Table(
    "identity_audit",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("at", String(40), nullable=False),
    Column("event", String(64), nullable=False),
    Column("actor_id", String(36)),
    Column("subject_id", String(36)),
)

USER_PERMISSIONS = frozenset({"diagnose", "view_sources", "submit_feedback", "propose_knowledge"})
CURATOR_PERMISSIONS = USER_PERMISSIONS | {"import_sources", "edit_candidates", "extract_candidates"}
ADMIN_PERMISSIONS = CURATOR_PERMISSIONS | {
    "review_knowledge",
    "publish_knowledge",
    "reject_knowledge",
    "withdraw_knowledge",
    "rollback_knowledge",
    "rebuild_index",
    "manage_skills",
    "manage_users",
}
PERMISSIONS = {
    Role.USER: USER_PERMISSIONS,
    Role.CURATOR: CURATOR_PERMISSIONS,
    Role.ADMIN: ADMIN_PERMISSIONS,
}


def audit(
    connection: Connection, event: str, actor_id: str | None = None, subject_id: str | None = None
) -> None:
    connection.execute(
        insert(audit_events).values(
            id=str(uuid4()),
            at=datetime.now(UTC).isoformat(),
            event=event,
            actor_id=actor_id,
            subject_id=subject_id,
        )
    )


def token_hash(token: str) -> str:
    # Tokens have 256 bits of random entropy; no low-entropy password is accepted here.
    return hashlib.sha256(token.encode()).hexdigest()


def to_user(row: Any) -> User:
    return User(row.id, row.username, Role(row.role), row.enabled, row.external_identity)


class Identity:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def open(cls, url: str | URL) -> "Identity":
        engine = create_engine(url, hide_parameters=True, pool_pre_ping=True)
        metadata.create_all(engine)
        return cls(engine)

    def close(self) -> None:
        self.engine.dispose()

    def check_ready(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(select(users.c.id).limit(1))

    def bootstrap(self, username: str) -> IssuedToken:
        validate_username(username)
        token = secrets.token_urlsafe(32)
        user = User(str(uuid4()), username, Role.ADMIN, True, None)
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(bootstrap_guard).values(id=1))
                connection.execute(
                    insert(users).values(
                        id=user.id,
                        username=username,
                        role=user.role.value,
                        enabled=True,
                        external_identity=None,
                        token_hash=token_hash(token),
                    )
                )
                audit(connection, "identity.bootstrap", user.id, user.id)
        except IntegrityError:
            raise IdentityError("Identity is already initialized") from None
        return IssuedToken(user, token)

    def authenticate(self, token: str) -> User:
        with self.engine.begin() as connection:
            row = connection.execute(
                select(users).where(
                    users.c.token_hash == token_hash(token), users.c.enabled.is_(True)
                )
            ).first()
            audit(
                connection,
                "auth.failed" if row is None else "auth.succeeded",
                None if row is None else row.id,
            )
        if row is None:
            raise IdentityError("Invalid or disabled credentials", 401)
        return to_user(row)

    def create_user(self, username: str, role: Role = Role.USER, *, actor_id: str) -> IssuedToken:
        validate_username(username)
        token = secrets.token_urlsafe(32)
        user = User(str(uuid4()), username, role, True, None)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(users).values(
                        id=user.id,
                        username=user.username,
                        role=role.value,
                        enabled=True,
                        external_identity=None,
                        token_hash=token_hash(token),
                    )
                )
                audit(connection, "user.created", actor_id, user.id)
        except IntegrityError:
            raise IdentityError("Username already exists") from None
        return IssuedToken(user, token)

    def list_users(self) -> list[User]:
        with self.engine.connect() as connection:
            return [
                to_user(row) for row in connection.execute(select(users).order_by(users.c.username))
            ]

    def reset_token(self, user_id: str, *, actor_id: str) -> IssuedToken:
        token = secrets.token_urlsafe(32)
        with self.engine.begin() as connection:
            row = connection.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(token_hash=token_hash(token))
                .returning(users)
            ).first()
            if row is None:
                raise IdentityError("User not found", 404)
            audit(connection, "token.reset", actor_id, user_id)
            return IssuedToken(to_user(row), token)

    def update_user(
        self, user_id: str, role: Role | None, enabled: bool | None, *, actor_id: str
    ) -> User:
        with self.engine.begin() as connection:
            # Serialize administrator changes, including the last-admin check, on both databases.
            connection.execute(
                update(bootstrap_guard).where(bootstrap_guard.c.id == 1).values(id=1)
            )
            row = connection.execute(select(users).where(users.c.id == user_id)).first()
            if row is None:
                raise IdentityError("User not found", 404)
            new_role = role if role is not None else Role(row.role)
            new_enabled = enabled if enabled is not None else row.enabled
            if (
                row.role == Role.ADMIN
                and row.enabled
                and (new_role != Role.ADMIN or not new_enabled)
            ):
                another_admin = connection.execute(
                    select(users.c.id).where(
                        users.c.id != user_id, users.c.role == Role.ADMIN, users.c.enabled.is_(True)
                    )
                ).first()
                if another_admin is None:
                    raise IdentityError("Cannot disable or demote the last enabled administrator")
            connection.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(role=new_role.value, enabled=new_enabled)
            )
            audit(connection, "user.updated", actor_id, user_id)
            return User(row.id, row.username, new_role, new_enabled, row.external_identity)

    def authorize(self, user: User, permission: str) -> None:
        if permission not in PERMISSIONS[user.role]:
            self.record_event("authorization.denied", user.id)
            raise IdentityError("Insufficient permission", 403)

    def record_event(self, event: str, actor_id: str | None = None) -> None:
        with self.engine.begin() as connection:
            audit(connection, event, actor_id)

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(audit_events).order_by(audit_events.c.at.desc()).limit(limit)
            )
            return [dict(row._mapping) for row in rows]


def validate_username(username: str) -> None:
    if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", username) is None:
        raise IdentityError(
            "Username must be 1-64 letters, digits, dots, underscores or hyphens", 422
        )
