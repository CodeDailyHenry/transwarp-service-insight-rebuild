import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar, cast

import pytest

from sla_assistant.cli import main


class ReadyBackendClient:
    def is_ready(self) -> bool:
        return True


class ReadyHandler(BaseHTTPRequestHandler):
    requested_paths: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        self.requested_paths.append(self.path)
        body = json.dumps({"status": "ready"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def ready_api_url() -> Iterator[str]:
    ReadyHandler.requested_paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), ReadyHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        host, port = cast(tuple[str, int], server.server_address)
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_cli_command_uses_controllable_backend_client(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["ready"], backend_client=ReadyBackendClient())

    assert capsys.readouterr().out.strip() == "SLA API is ready"


def test_installed_cli_accesses_configured_backend(ready_api_url: str) -> None:
    executable = Path(sys.executable).with_name("sla.exe" if os.name == "nt" else "sla")
    environment = os.environ.copy()
    environment["SLA_API_URL"] = ready_api_url

    result = subprocess.run(
        [str(executable), "ready"],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "SLA API is ready"
    assert ReadyHandler.requested_paths == ["/health/ready"]
