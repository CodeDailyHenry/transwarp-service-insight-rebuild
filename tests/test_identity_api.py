from collections.abc import Iterator

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import URL

from sla_assistant.api import create_app
from sla_assistant.identity import Identity
from sla_assistant.security import require_permission


@pytest.fixture
def client(identity_url: str | URL) -> Iterator[TestClient]:
    identity = Identity.open(identity_url)
    admin = identity.bootstrap("maintainer")
    with TestClient(create_app(identity)) as client:
        client.headers["Authorization"] = f"Bearer {admin.token}"
        yield client
    identity.close()


def test_admin_creates_default_user_and_token_is_only_returned_once(client: TestClient) -> None:
    response = client.post("/v1/admin/users", json={"username": "support"})
    assert response.status_code == 201
    issued = response.json()
    assert issued["user"]["role"] == "user"
    assert response.headers["cache-control"] == "no-store"
    assert "token" not in client.get("/v1/admin/users").text
    assert issued["token"] not in client.get("/v1/admin/users").text

    headers = {"Authorization": f"Bearer {issued['token']}"}
    me = client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "support"
    assert client.get("/v1/admin/users", headers=headers).status_code == 403
    assert (
        client.post(
            "/v1/admin/users", json={"username": "intruder", "role": "admin"}, headers=headers
        ).status_code
        == 403
    )
    assert client.get("/v1/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_reset_disable_and_role_changes_take_effect_on_next_request(client: TestClient) -> None:
    issued = client.post("/v1/admin/users", json={"username": "support"}).json()
    user_id = issued["user"]["id"]
    old_headers = {"Authorization": f"Bearer {issued['token']}"}
    reset = client.post(f"/v1/admin/users/{user_id}/reset-token")
    assert reset.status_code == 200
    assert reset.headers["cache-control"] == "no-store"
    headers = {"Authorization": f"Bearer {reset.json()['token']}"}
    assert client.get("/v1/auth/me", headers=old_headers).status_code == 401
    assert client.get("/v1/auth/me", headers=headers).status_code == 200
    assert client.patch(f"/v1/admin/users/{user_id}", json={"role": "curator"}).status_code == 200
    assert client.get("/v1/auth/me", headers=headers).json()["role"] == "curator"
    assert client.patch(f"/v1/admin/users/{user_id}", json={"enabled": False}).status_code == 200
    assert client.get("/v1/auth/me", headers=headers).status_code == 401


def test_last_admin_cannot_be_disabled_or_demoted(client: TestClient) -> None:
    admin_id = client.get("/v1/auth/me").json()["id"]
    for change in ({"enabled": False}, {"role": "user"}):
        assert client.patch(f"/v1/admin/users/{admin_id}", json=change).status_code == 409
    assert client.get("/v1/auth/me").status_code == 200


@pytest.mark.parametrize("role", ["user", "curator", "admin"])
@pytest.mark.parametrize(
    "permission,allowed",
    [
        ("diagnose", {"user", "curator", "admin"}),
        ("view_sources", {"user", "curator", "admin"}),
        ("submit_feedback", {"user", "curator", "admin"}),
        ("propose_knowledge", {"user", "curator", "admin"}),
        ("import_sources", {"curator", "admin"}),
        ("edit_candidates", {"curator", "admin"}),
        ("extract_candidates", {"curator", "admin"}),
        ("review_knowledge", {"admin"}),
        ("publish_knowledge", {"admin"}),
        ("reject_knowledge", {"admin"}),
        ("withdraw_knowledge", {"admin"}),
        ("rollback_knowledge", {"admin"}),
        ("rebuild_index", {"admin"}),
        ("manage_skills", {"admin"}),
        ("manage_users", {"admin"}),
    ],
)
def test_http_permission_matrix(
    client: TestClient, role: str, permission: str, allowed: set[str]
) -> None:
    # Exercise the production guard without pretending W03-W13 business endpoints exist.
    from typing import cast

    from fastapi import FastAPI

    app = cast(FastAPI, client.app)
    app.add_api_route(
        "/test-protected",
        lambda: {"ok": True},
        dependencies=[Depends(require_permission(permission))],
    )
    issued = client.post("/v1/admin/users", json={"username": role, "role": role}).json()
    headers = {"Authorization": f"Bearer {issued['token']}"}
    assert client.get("/test-protected", headers=headers).status_code == (
        200 if role in allowed else 403
    )


def test_audit_tracks_operations_without_credentials(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    issued = client.post("/v1/admin/users", json={"username": "support"}).json()
    user_id = issued["user"]["id"]
    headers = {"Authorization": f"Bearer {issued['token']}"}
    client.get("/v1/admin/users", headers=headers)
    client.get("/v1/auth/me", headers={"Authorization": "Bearer secret-invalid-token"})
    reset = client.post(f"/v1/admin/users/{user_id}/reset-token").json()
    client.patch(f"/v1/admin/users/{user_id}", json={"enabled": False})
    audit = client.get("/v1/admin/audit")
    assert audit.status_code == 200
    events = {entry["event"] for entry in audit.json()}
    assert {
        "identity.bootstrap",
        "user.created",
        "token.reset",
        "user.updated",
        "auth.succeeded",
        "auth.failed",
        "authorization.denied",
    } <= events
    for token in (issued["token"], reset["token"], "secret-invalid-token"):
        assert token not in audit.text + caplog.text
    assert client.get("/v1/admin/audit", headers=headers).status_code == 401


@pytest.mark.parametrize("role", ["user", "curator"])
def test_every_account_management_endpoint_rejects_lower_roles(
    client: TestClient, role: str
) -> None:
    issued = client.post("/v1/admin/users", json={"username": role, "role": role}).json()
    user_id = issued["user"]["id"]
    headers = {"Authorization": f"Bearer {issued['token']}"}
    assert client.get("/v1/admin/users", headers=headers).status_code == 403
    assert client.get("/v1/admin/audit", headers=headers).status_code == 403
    assert (
        client.post("/v1/admin/users", headers=headers, json={"username": "new"}).status_code == 403
    )
    assert client.post(f"/v1/admin/users/{user_id}/reset-token", headers=headers).status_code == 403
    assert (
        client.patch(
            f"/v1/admin/users/{user_id}", headers=headers, json={"role": "admin"}
        ).status_code
        == 403
    )


def test_missing_credentials_and_invalid_account_changes(client: TestClient) -> None:
    client.headers.pop("Authorization")
    for path in ("/v1/auth/me", "/v1/admin/users", "/v1/admin/audit"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_duplicate_and_invalid_accounts_do_not_break_following_requests(client: TestClient) -> None:
    assert client.post("/v1/admin/users", json={"username": "support"}).status_code == 201
    assert client.post("/v1/admin/users", json={"username": "support"}).status_code == 409
    for body in ({"username": "../invalid"}, {"username": "new", "role": "root"}):
        assert client.post("/v1/admin/users", json=body).status_code == 422
    assert client.post("/v1/admin/users/missing/reset-token").status_code == 404
    assert client.patch("/v1/admin/users/missing", json={"enabled": False}).status_code == 404
    assert client.get("/v1/admin/users").status_code == 200
