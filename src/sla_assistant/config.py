import os
from pathlib import Path

from sqlalchemy import URL


def database_url() -> str | URL:
    if url := os.environ.get("SLA_DATABASE_URL"):
        return url
    if password_file := os.environ.get("SLA_DATABASE_PASSWORD_FILE"):
        return URL.create(
            "postgresql+psycopg",
            username=os.environ.get("SLA_DATABASE_USER", "sla"),
            password=Path(password_file).read_text(encoding="utf-8").strip(),
            host=os.environ.get("SLA_DATABASE_HOST", "db"),
            database=os.environ.get("SLA_DATABASE_NAME", "sla"),
        )
    return "sqlite:///sla-assistant.db"
