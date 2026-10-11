import asyncio
import io
from uuid import uuid4

import pytest
from PIL import Image

from app.evidence.processing import process_media
from app.shared.jobs.executor import ExecutorRegistry
from app.shared.jobs.worker import Worker
from tests.acceptance.test_resource_access import fixture_client


def png(color="red"):
    output = io.BytesIO()
    Image.new("RGB", (24, 24), color).save(output, format="PNG")
    return output.getvalue()


def event():
    client = fixture_client("engineer")
    response = client.post(
        "/api/incidents", json={"raw_description": "A310"}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert response.status_code == 200
    return client, response.json()["incident_id"]


def upload(client, incident, data, content_type="image/png", key=None):
    return client.post(
        f"/api/incidents/{incident}/media",
        files={"file": ("现场.png", data, content_type)},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def test_private_minio_upload_duplicate_guard_and_truthful_failure():
    client, incident = event()
    data = png()
    result = upload(client, incident, data)
    assert result.status_code == 200, result.text
    media = result.json()
    assert media["scan_status"] == "NOT_PERFORMED"
    assert "storage_ref" not in media
    assert upload(client, incident, data).status_code == 409
    content = client.get(f"/api/media/{media['media_id']}/content")
    assert content.content == data and content.headers["cache-control"] == "no-store"
    outsider = fixture_client("expert")
    assert outsider.get(f"/api/media/{media['media_id']}/content").status_code == 404
    registry = ExecutorRegistry()
    registry.register("OCR", process_media)
    worker = Worker(registry)
    for _ in range(50):
        job = client.get(f"/api/jobs/{media['job_id']}").json()
        if job["status"] in {"SUCCEEDED", "FAILED", "TIMED_OUT"}:
            break
        assert asyncio.run(worker.run_once())
    assert job["status"] == "SUCCEEDED"
    assert job["result_ref"] == media["media_id"]
    evidence = client.get(f"/api/incidents/{incident}/evidence").json()["evidence"]
    failures = [row for row in evidence if row["media_id"] == media["media_id"]]
    assert len(failures) == 3 and {row["source"] for row in failures} == {"OCR", "VISION", "QR"}
    assert all(row["state"] == "UNAVAILABLE" and row["value"]["value"] is None for row in failures)
    from tests.acceptance.test_a203 import execute

    started = client.post(
        f"/api/incidents/{incident}/diagnoses", json={}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert started.status_code == 200, started.text
    execute(started.json()["job_id"])
    fallback = client.get(f"/api/diagnoses/{started.json()['diagnosis_run_id']}").json()
    assert fallback["state"] == "NEEDS_INFORMATION" and fallback["report"] is None


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"not an image", "image/png"),
        (png(), "image/jpeg"),
        (b"<svg><script/></svg>", "image/svg+xml"),
    ],
)
def test_actual_decode_rejects_fake_type_or_executable_content(data, mime):
    client, incident = event()
    rejected = upload(client, incident, data, mime)
    assert rejected.status_code == 422


def test_image_count_and_write_access_are_enforced():
    client, incident = event()
    for color in ("red", "green", "blue", "yellow", "purple"):
        response = upload(client, incident, png(color))
        assert response.status_code == 200, response.text
    assert upload(client, incident, png("black")).status_code == 413
    assert upload(fixture_client("expert"), incident, png()).status_code == 404
