from fastapi.testclient import TestClient

from sla_assistant.api import app


def test_readiness_endpoint_reports_service_is_ready() -> None:
    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
