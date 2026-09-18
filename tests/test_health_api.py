from fastapi.testclient import TestClient
from sqlalchemy import URL

from sla_assistant.api import create_app
from sla_assistant.identity import Identity


def test_readiness_endpoint_reports_service_is_ready(identity_url: str | URL) -> None:
    identity = Identity.open(identity_url)
    with TestClient(create_app(identity)) as client:
        response = client.get("/health/ready")
        assert client.get("/health/live").status_code == 200
    identity.close()

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
