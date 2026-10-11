from fastapi.testclient import TestClient

from app.main import app


def test_unexpected_error_omits_exception_and_has_server_trace():
    async def private_failure():
        raise RuntimeError("private password /private/path")

    app.add_api_route("/_test/private-failure", private_failure, methods=["GET"])
    try:
        response = TestClient(app).get("/_test/private-failure")
        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"
        assert response.json()["trace_id"] == response.headers["X-Trace-ID"]
        assert "private" not in response.text
    finally:
        app.router.routes[:] = [
            route
            for route in app.router.routes
            if getattr(route, "path", "") != "/_test/private-failure"
        ]
