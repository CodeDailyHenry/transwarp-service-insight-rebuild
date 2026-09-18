import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def identity_url(tmp_path: Path) -> Iterator[str | URL]:
    """Each PostgreSQL test owns a new schema; never clear an existing database."""
    if not (url := os.environ.get("SLA_TEST_POSTGRES_URL")):
        yield f"sqlite:///{tmp_path / 'identity.db'}"
        return
    schema = f"test_identity_{uuid4().hex}"
    engine = create_engine(url, hide_parameters=True)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
