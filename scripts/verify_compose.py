"""Run an isolated Compose smoke test; never print generated credentials."""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    project = f"sla-verify-{uuid4().hex[:12]}"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment["SLA_API_PORT"] = str(port)
    with tempfile.TemporaryDirectory(prefix="sla-compose-") as temporary:
        directory = Path(temporary)
        password = directory / "postgres_password.txt"
        password.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        override = directory / "compose.override.json"
        override.write_text(
            json.dumps({"secrets": {"postgres_password": {"file": str(password)}}}),
            encoding="utf-8",
        )
        command = [
            "docker",
            "compose",
            "--project-name",
            project,
            "-f",
            str(root / "compose.yaml"),
            "-f",
            str(override),
        ]

        def compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [*command, *args],
                cwd=root,
                env=environment,
                text=True,
                capture_output=capture,
                check=False,
            )

        def checked(*args: str) -> None:
            if compose(*args).returncode:
                raise RuntimeError(f"Compose failed: {args[0]}")

        def request(
            path: str,
            *,
            token: str | None = None,
            method: str = "GET",
            body: dict[str, Any] | None = None,
            expected: int = 200,
        ) -> Any:
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                method=method,
                headers=headers,
                data=None if body is None else json.dumps(body).encode(),
            )
            try:
                response = urllib.request.urlopen(req, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                if response.status != expected:
                    raise RuntimeError(
                        f"{method} {path}: expected {expected}, got {response.status}"
                    )
                result = json.load(response)
                if isinstance(result, dict) and "token" in result:
                    assert response.headers["Cache-Control"] == "no-store"
                return result

        try:
            print(f"Starting isolated Compose project {project}", flush=True)
            checked("up", "--build", "--detach", "--wait", "--wait-timeout", "180")
            assert request("/health/ready") == {"status": "ready"}
            assert request("/health/live") == {"status": "live"}
            cli = subprocess.run(
                [
                    str(Path(sys.executable).with_name("sla.exe" if os.name == "nt" else "sla")),
                    "ready",
                    "--api-url",
                    f"http://127.0.0.1:{port}",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            # Use the installed host CLI: this also verifies published-port connectivity.
            assert cli.returncode == 0 and "SLA API is ready" in cli.stdout
            print("PASS: container health, host HTTP and installed CLI", flush=True)

            bootstrap = compose(
                "exec",
                "-T",
                "api",
                "sla-admin",
                "bootstrap",
                "--username",
                "smoke-admin",
                capture=True,
            )
            if bootstrap.returncode:
                raise RuntimeError("Administrator bootstrap failed")
            admin = json.loads(bootstrap.stdout)["token"]
            request("/v1/auth/me", expected=401)
            assert request("/v1/auth/me", token=admin)["role"] == "admin"
            issued = request(
                "/v1/admin/users",
                token=admin,
                method="POST",
                body={"username": "smoke-user"},
                expected=201,
            )
            assert issued["user"]["role"] == "user"
            user_id, original = issued["user"]["id"], issued["token"]
            request("/v1/admin/users", token=original, expected=403)
            request(
                f"/v1/admin/users/{user_id}",
                token=original,
                method="PATCH",
                body={"role": "admin"},
                expected=403,
            )
            curator = request(
                "/v1/admin/users",
                token=admin,
                method="POST",
                body={"username": "smoke-curator", "role": "curator"},
                expected=201,
            )
            request("/v1/admin/users", token=curator["token"], expected=403)
            reset = request(f"/v1/admin/users/{user_id}/reset-token", token=admin, method="POST")
            renewed = reset["token"]
            request("/v1/auth/me", token=original, expected=401)
            request("/v1/auth/me", token=renewed)
            request(
                f"/v1/admin/users/{user_id}", token=admin, method="PATCH", body={"enabled": False}
            )
            request("/v1/auth/me", token=renewed, expected=401)
            request(
                f"/v1/admin/users/{user_id}", token=admin, method="PATCH", body={"enabled": True}
            )
            print("PASS: bootstrap, three roles, reset and account disablement", flush=True)

            checked("down")
            checked("up", "--detach", "--wait", "--wait-timeout", "180")
            assert request("/v1/auth/me", token=admin)["username"] == "smoke-admin"
            assert request("/v1/auth/me", token=renewed)["id"] == user_id
            request("/v1/auth/me", token=original, expected=401)
            repeated = compose(
                "exec",
                "-T",
                "api",
                "sla-admin",
                "bootstrap",
                "--username",
                "another-admin",
                capture=True,
            )
            assert repeated.returncode != 0 and not repeated.stdout.strip()
            assert "already initialized" in repeated.stderr
            print("PASS: PostgreSQL volume persistence and one-time bootstrap", flush=True)

            audit = request("/v1/admin/audit", token=admin)
            assert {
                "identity.bootstrap",
                "user.created",
                "token.reset",
                "user.updated",
                "auth.failed",
                "authorization.denied",
            } <= {event["event"] for event in audit}
            logs = compose("logs", "--no-color", capture=True)
            assert logs.returncode == 0
            exposed = json.dumps(audit) + logs.stdout + logs.stderr
            assert all(
                token not in exposed for token in (admin, original, renewed, curator["token"])
            )
            print("PASS: persistent audit and no tokens in container logs", flush=True)
        finally:
            # Only the randomly named project created by this invocation is removed.
            checked("down", "--volumes", "--remove-orphans")
        print(
            "PASS: Compose verification complete; temporary containers and volume removed",
            flush=True,
        )


if __name__ == "__main__":
    main()
