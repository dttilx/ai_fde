from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_fixture_mode():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "FIXTURE"
