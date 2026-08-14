import argparse
import os
from collections.abc import Sequence
from typing import Protocol

from sla_assistant.backend_client import HttpBackendClient

DEFAULT_API_URL = "http://127.0.0.1:8000"


class BackendClient(Protocol):
    def is_ready(self) -> bool: ...


def main(
    argv: Sequence[str] | None = None,
    *,
    backend_client: BackendClient | None = None,
) -> None:
    parser = argparse.ArgumentParser(prog="sla")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ready_parser = subparsers.add_parser("ready", help="check backend readiness")
    ready_parser.add_argument(
        "--api-url",
        default=os.environ.get("SLA_API_URL", DEFAULT_API_URL),
        help="backend base URL (default: %(default)s)",
    )

    args = parser.parse_args(argv)
    if args.command == "ready":
        client = backend_client or HttpBackendClient(args.api_url)
        if not client.is_ready():
            raise RuntimeError("SLA API is not ready")
        print("SLA API is ready")
