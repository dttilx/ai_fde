from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.access.models import User
from app.access.session import hasher
from app.main import app
from app.shared.config import settings


def test_server_role_csrf_logout_and_disabled_session():
    admin = create_engine(settings().migration_database_url.get_secret_value())
    name = "test-" + uuid4().hex
    with Session(admin) as db, db.begin():
        user = User(
            username=name,
            password_hash=hasher.hash("fixture-test-password"),
            roles=["FIELD_ENGINEER"],
        )
        db.add(user)
        db.flush()
        user_id = user.id
    client = TestClient(app)
    assert client.get("/api/me").status_code == 401
    spoof = client.post(
        "/api/session",
        json={"username": name, "password": "fixture-test-password", "role": "EXPERT"},
    )
    assert spoof.status_code == 422
    assert "password" not in spoof.text
    login = client.post(
        "/api/session", json={"username": name, "password": "fixture-test-password"}
    )
    assert login.status_code == 200
    assert "httponly" in login.headers["set-cookie"].lower()
    csrf = login.json()["csrf_token"]
    assert client.get("/api/me").json()["roles"] == ["FIELD_ENGINEER"]
    assert client.delete("/api/session").status_code == 403
    assert client.delete("/api/session", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.delete("/api/session").status_code == 204
    assert client.get("/api/me").status_code == 401
    client.post("/api/session", json={"username": name, "password": "fixture-test-password"})
    with Session(admin) as db, db.begin():
        user = db.get(User, user_id)
        user.enabled = False
        user.auth_version += 1
    assert client.get("/api/me").status_code == 401


def test_role_is_not_maintenance_qualification():
    from app.safety.service import evaluate

    assert evaluate("", {}, requested_actions=("检查线路",)).escalate_expert


def test_login_failures_are_throttled_and_do_not_echo_input():
    client = TestClient(app)
    name = "absent-" + uuid4().hex
    for _ in range(10):
        response = client.post("/api/session", json={"username": name, "password": "not-secret"})
        assert response.status_code == 401
        assert name not in response.text
    assert (
        client.post("/api/session", json={"username": name, "password": "not-secret"}).status_code
        == 429
    )
