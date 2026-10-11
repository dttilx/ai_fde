import asyncio
import tempfile
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from sqlalchemy import select

from app.access.models import User
from app.evidence.ocr import FixtureOCR
from app.evidence.processing import process_media
from app.evidence.qr import decode_qr, resolve_qr
from app.evidence.video import decode_video
from app.incidents.service import current_snapshot
from app.shared.auth_context import ActorContext
from app.shared.config import PROJECT_ROOT, settings
from app.shared.db import session_factory
from app.shared.jobs.executor import ExecutorRegistry
from app.shared.jobs.worker import Worker
from tests.acceptance.test_media_upload import event, png, upload


def execute_media(client, job_id, kind):
    registry = ExecutorRegistry()
    registry.register(kind, process_media)
    worker = Worker(registry)
    for _ in range(100):
        response = client.get(f"/api/jobs/{job_id}").json()
        if response["status"] in {"SUCCEEDED", "FAILED", "TIMED_OUT"}:
            assert response["status"] == "SUCCEEDED", response
            return
        if not asyncio.run(worker.run_once()):
            # The application worker may already own this job in integration runs.
            continue
    raise AssertionError("media Job did not complete")


def test_checksum_bound_fixture_candidates_never_become_current_facts():
    client, incident = event()
    data = (PROJECT_ROOT / "knowledge/fixtures/media/a203-panel-fixture.png").read_bytes()
    response = upload(client, incident, data)
    assert response.status_code == 200, response.text
    media = response.json()
    execute_media(client, media["job_id"], "OCR")
    rows = client.get(f"/api/incidents/{incident}/evidence").json()["evidence"]
    recognized = [
        r for r in rows if r["media_id"] == media["media_id"] and r["state"] == "CANDIDATE"
    ]
    if settings().ocr_provider == "rapidocr":
        assert recognized
        assert all(r["source"] == "OCR" for r in recognized)
    else:
        assert len(recognized) == 4
        assert all(r["source"] == "OCR" and r["locators"]["region"] for r in recognized)
    with session_factory()() as db:
        snapshot = current_snapshot(db, incident)
        assert snapshot.facts == {"alarm_code": "A310"}
        assert not set(r["evidence_id"] for r in recognized).intersection(snapshot.evidence_ids)
    assert FixtureOCR().analyze(png())["candidates"] == []


def test_real_qr_decoder_and_authorized_asset_resolution_do_not_invent_causes():
    with session_factory()() as db:
        user = db.scalar(select(User).where(User.username == "engineer"))
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        outcomes = []
        for index in range(4):
            data = (PROJECT_ROOT / f"knowledge/fixtures/media/qr-{index}.png").read_bytes()
            decoded = decode_qr(data)
            assert decoded["candidate"] is not None
            outcomes.append(resolve_qr(db, actor, decoded["candidate"]))
        assert outcomes[0]["candidate"]["asset_context"]["model"] == "APX-240"
        assert outcomes[1]["candidate"]["asset_context"]["history_refs"] == []
        assert outcomes[2]["candidate"] is None and "型号" in outcomes[2]["limitation"]
        assert outcomes[3]["candidate"] is None and "未知或不可访问" in outcomes[3]["limitation"]
    assert decode_qr(png())["candidate"] is None


def video_bytes():
    with tempfile.TemporaryDirectory(prefix="apx_test_video_") as folder:
        path = Path(folder) / "dark.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
        assert writer.isOpened(), (
            "Local test encoder must work; do not replace with a successful fixture"
        )
        try:
            for _ in range(20):
                writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
        finally:
            writer.release()
        return path.read_bytes()


def test_real_bounded_video_frames_and_dark_failure_locators():
    data = video_bytes()
    decoded = decode_video(data, "video/mp4", frames=True)
    assert len(decoded["frames"]) == 8
    assert all(frame["dark"] and frame["bytes"] for frame in decoded["frames"])
    assert decoded["frames"][0]["timestamp_ms"] == 0
    assert decoded["frames"][-1]["timestamp_ms"] > 0
    client, incident = event()
    response = client.post(
        f"/api/incidents/{incident}/media",
        files={"file": ("dark.mp4", data, "video/mp4")},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 200, response.text
    execute_media(client, response.json()["job_id"], "VIDEO")
    rows = client.get(f"/api/incidents/{incident}/evidence").json()["evidence"]
    failures = [r for r in rows if r["media_id"] == response.json()["media_id"]]
    assert len(failures) == 8 and all(r["state"] == "UNAVAILABLE" for r in failures)
    assert all(
        "过暗" in r["value"]["limitation"] and "timestamp_ms" in r["locators"] for r in failures
    )
