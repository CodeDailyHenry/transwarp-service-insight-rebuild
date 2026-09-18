"""Host-only deployment command, deliberately separate from the HTTP client CLI."""

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict

from sqlalchemy.exc import SQLAlchemyError

from sla_assistant.config import database_url
from sla_assistant.identity import Identity, IdentityError


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sla-admin")
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap", help="initialize the first administrator once")
    bootstrap.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    try:
        identity = Identity.open(database_url())
        try:
            issued = identity.bootstrap(args.username)
            print(json.dumps(asdict(issued)))
        finally:
            identity.close()
    except IdentityError as exc:
        parser.exit(1, f"{exc}\n")
    except (SQLAlchemyError, OSError):
        # Connection exceptions may include deployment credentials. Do not print their details.
        parser.exit(1, "Identity database is unavailable; check deployment configuration.\n")


if __name__ == "__main__":
    main()
