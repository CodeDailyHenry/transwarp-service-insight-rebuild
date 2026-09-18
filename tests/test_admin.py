import json
import os
import subprocess
import sys
from pathlib import Path

from sla_assistant.identity import Identity


def test_deployment_bootstrap_prints_token_once_and_persists_only_hash(tmp_path: Path) -> None:
    database = tmp_path / "identity.db"
    environment = os.environ.copy()
    environment["SLA_DATABASE_URL"] = f"sqlite:///{database}"
    command = [sys.executable, "-m", "sla_assistant.admin", "bootstrap", "--username", "maintainer"]
    first = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    issued = json.loads(first.stdout)
    identity = Identity.open(environment["SLA_DATABASE_URL"])
    assert identity.authenticate(issued["token"]).role == "admin"
    identity.close()
    second = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    assert second.returncode != 0
    assert second.stdout == ""
    assert "already initialized" in second.stderr
    assert issued["token"] not in first.stderr + second.stdout + second.stderr
    # At the persistence boundary, a copied database must not contain bearer credentials.
    assert issued["token"].encode() not in database.read_bytes()
