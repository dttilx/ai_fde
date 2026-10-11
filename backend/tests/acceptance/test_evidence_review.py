from uuid import uuid4

from sqlalchemy import select

from app.access.models import PolicyBinding
from app.diagnosis.models import DiagnosisRun, ReportVersion
from app.incidents.models import Evidence
from app.incidents.service import current_snapshot
from app.shared.config import PROJECT_ROOT, settings
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create, execute
from tests.acceptance.test_media_candidates import execute_media
from tests.acceptance.test_media_upload import event, upload


def candidates(client, incident):
    data = (PROJECT_ROOT / "knowledge/fixtures/media/a203-panel-fixture.png").read_bytes()
    uploaded = upload(client, incident, data)
    assert uploaded.status_code == 200
    execute_media(client, uploaded.json()["job_id"], "OCR")
    return [
        r
        for r in client.get(f"/api/incidents/{incident}/evidence").json()["evidence"]
        if r["reviewable"]
    ]


def decision(row, kind="CONFIRMED", corrected=None):
    return {
        "evidence_id": row["evidence_id"],
        "expected_evidence_version": row["version"],
        "decision": kind,
        "corrected_content": corrected,
        "review_note": "人工对照原图逐项核实。",
    }


def batch(client, incident, decisions, key=None):
    return client.post(
        f"/api/incidents/{incident}/evidence/review-batch",
        json={"decisions": decisions},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def test_confirmed_conflict_blocks_safety_and_preserves_original_candidates():
    client, incident = event()
    rows = candidates(client, incident)
    blocked = client.post(
        f"/api/incidents/{incident}/diagnoses", json={}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "MEDIA_REVIEW_REQUIRED"
    reviewed = batch(client, incident, [decision(row) for row in rows])
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["conflicts"] == ["alarm_code"]
    started = client.post(
        f"/api/incidents/{incident}/diagnoses", json={}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert started.status_code == 200
    execute(started.json()["job_id"])
    result = client.get(f"/api/diagnoses/{started.json()['diagnosis_run_id']}").json()
    assert result["state"] == "CONFLICT_BLOCKED" and result["report"] is None
    assert "retrieve" not in [n["node"] for n in result["timeline"]]
    with session_factory()() as db:
        assert all(db.get(Evidence, row["evidence_id"]).state == "CANDIDATE" for row in rows)


def test_correct_reject_and_stale_batch_are_atomic_without_implicit_accept():
    client, incident = event()
    rows = candidates(client, incident)
    first, fresh = rows[:2]
    review = batch(client, incident, [decision(first, "REJECTED")])
    assert review.status_code == 200
    with session_factory()() as db:
        snapshot_id = current_snapshot(db, incident).id
    stale = batch(client, incident, [decision(first), decision(fresh)])
    assert stale.status_code == 409
    with session_factory()() as db:
        assert current_snapshot(db, incident).id == snapshot_id
        assert not db.scalar(
            select(Evidence.id).where(Evidence.supersedes_id == fresh["evidence_id"])
        )
    key = uuid4().hex
    corrected = batch(client, incident, [decision(fresh, "CORRECTED", {"value": 166})], key)
    assert corrected.status_code == 200, corrected.text
    assert batch(client, incident, [decision(fresh)], key).status_code == 409
    with session_factory()() as db:
        assert db.get(Evidence, fresh["evidence_id"]).state == "CANDIDATE"


def test_changed_confirmed_image_invalidates_report_review_and_rechecks_safety():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    state = client.get(f"/api/diagnoses/{run_id}").json()
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    rows = candidates(client, state["incident_id"])
    decisions = [
        decision(row, "CORRECTED", {"value": 160})
        if row["key"] == "actual_temperature_c"
        else decision(row, "REJECTED")
        for row in rows
    ]
    assert batch(client, state["incident_id"], decisions).status_code == 200
    resumed = client.post(
        f"/api/diagnoses/{run_id}/resume",
        json={
            "type": "REPORT_REVIEW",
            "interrupt_id": cp["interrupt_id"],
            "expected_checkpoint_version": cp["checkpoint_version"],
            "idempotency_key": uuid4().hex,
            "report_version_id": state["report"]["report_version_id"],
            "report_hash": state["report_hash"],
        },
    )
    assert resumed.status_code == 200, resumed.text
    execute(resumed.json()["job_id"])
    stopped = client.get(f"/api/diagnoses/{run_id}").json()
    assert stopped["state"] == "CONFLICT_BLOCKED" and stopped["report"] is None
    assert stopped["immediate_safety_notice"]["safety_blocked"]
    assert sum(n["node"] == "retrieve" for n in stopped["timeline"]) == sum(
        n["node"] == "retrieve" for n in state["timeline"]
    )
    with session_factory()() as db:
        assert db.get(DiagnosisRun, run_id).graph_thread_id == run_id
        assert (
            db.get(ReportVersion, state["report"]["report_version_id"]).payload[
                "publication_status"
            ]
            == "DRAFT"
        )


def test_confirmed_media_report_access_tracks_original_evidence_revocation():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    state = client.get(f"/api/diagnoses/{run_id}").json()
    rows = candidates(client, state["incident_id"])
    assert batch(client, state["incident_id"], [decision(row) for row in rows]).status_code == 200
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    resumed = client.post(
        f"/api/diagnoses/{run_id}/resume",
        json={
            "type": "REPORT_REVIEW",
            "interrupt_id": cp["interrupt_id"],
            "expected_checkpoint_version": cp["checkpoint_version"],
            "idempotency_key": uuid4().hex,
            "report_version_id": state["report"]["report_version_id"],
            "report_hash": state["report_hash"],
        },
    )
    assert resumed.status_code == 200, resumed.text
    execute(resumed.json()["job_id"])
    current = client.get(f"/api/diagnoses/{run_id}")
    assert current.status_code == 200, current.text
    assert current.json()["report"]["publication_status"] == "DRAFT"
    expected = 5 if settings().ocr_provider == "rapidocr" else 4
    assert len(current.json()["report"]["confirmed_observations"]) == expected
    # Revoke the immutable candidate's policy after a derived CONFIRMED version exists.
    # Current derived policy alone must not retain access to its original input.
    with session_factory()() as db, db.begin():
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "EVIDENCE",
                PolicyBinding.resource_id == rows[0]["evidence_id"],
            )
        )
        assert policy is not None
        policy.readable_by = []
        policy.version += 1
    assert client.get(f"/api/diagnoses/{run_id}").status_code == 404
    assert client.get(f"/api/diagnoses/{run_id}/checkpoint").status_code == 404
    assert client.get(f"/api/jobs/{resumed.json()['job_id']}").status_code == 404
    # The private original image has a separate permission and can still be viewed.
    assert client.get(f"/api/media/{rows[0]['media_id']}/content").status_code == 200
