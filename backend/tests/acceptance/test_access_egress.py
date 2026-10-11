"""Resource, checkpoint and provider-egress boundary checks."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from app.shared.providers.data_profile import ProcessingGrant, ProviderDataProfile
from app.shared.providers.egress import authorize_egress
from tests.acceptance import test_resource_access as access_tests
from tests.acceptance.test_a203 import execute
from tests.acceptance.test_resource_access import fixture_client


def test_cross_role_cannot_read_run_checkpoint_or_event_stream():
    engineer = fixture_client("engineer")
    expert = fixture_client("expert")
    created = engineer.post(
        "/api/incidents",
        json={"raw_description": "A203，设定165，实际128，加热电流0，已预热"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 200
    incident_id = created.json()["incident_id"]
    started = engineer.post(
        f"/api/incidents/{incident_id}/diagnoses",
        json={},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert started.status_code == 200
    execute(started.json()["job_id"])
    run_id = started.json()["diagnosis_run_id"]
    assert expert.get(f"/api/diagnoses/{run_id}").status_code == 404
    assert expert.get(f"/api/diagnoses/{run_id}/checkpoint").status_code == 404
    assert expert.get(f"/api/jobs/{started.json()['job_id']}").status_code == 404
    assert expert.get(f"/api/diagnoses/{run_id}/retrieval-assessments").status_code == 404
    assert expert.get(f"/api/diagnoses/{run_id}/citation-assessments").status_code == 404
    assert expert.post(
        f"/api/diagnoses/{run_id}/linked-runs",
        json={"source_scope": ["unknown-source"], "reason": "越权测试"},
        headers={"Idempotency-Key": uuid4().hex},
    ).status_code in {403, 404}
    assert expert.get(f"/api/incidents/{incident_id}").status_code == 404
    # SSE performs the same resource check before opening a streaming response.
    assert expert.get(f"/api/incidents/{incident_id}/events").status_code == 404


def test_event_stream_rechecks_session_revocation_before_delivery():
    from sqlalchemy import select

    from app.access.models import User
    from app.shared.db import session_factory

    engineer = fixture_client("engineer")
    created = engineer.post(
        "/api/incidents",
        json={"raw_description": "A203，设定165，实际128，加热电流0，已预热"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 200
    incident_id = created.json()["incident_id"]
    with session_factory()() as db, db.begin():
        user = db.scalar(select(User).where(User.username == "engineer"))
        user.enabled = False
        user.auth_version += 1
    try:
        assert engineer.get(f"/api/incidents/{incident_id}/events").status_code in {401, 403, 404}
    finally:
        with session_factory()() as db, db.begin():
            user = db.scalar(select(User).where(User.username == "engineer"))
            user.enabled = True
            user.auth_version += 1


def test_session_revocation_is_append_only_audited():
    from sqlalchemy import select

    from app.shared.audit import AuditRecord
    from app.shared.db import session_factory

    engineer = fixture_client("engineer")
    actor_id = engineer.get("/api/me").json()["user_id"]
    assert engineer.delete("/api/session").status_code == 204
    with session_factory()() as db:
        record = db.scalar(
            select(AuditRecord)
            .where(AuditRecord.actor_id == actor_id, AuditRecord.action == "SESSION_REVOKED")
            .order_by(AuditRecord.created_at.desc())
        )
        assert record is not None
        with pytest.raises(DBAPIError, match="APPEND_ONLY_RECORD"):
            db.delete(record)
            db.flush()


def test_public_diagnosis_projection_contains_hashes_and_citations_not_raw_provider_payload():
    engineer = fixture_client("engineer")
    raw = "A203，设定165，实际128，加热电流0，已预热。SECRET-RAW-IDENTITY"
    created = engineer.post(
        "/api/incidents",
        json={"raw_description": raw, "alarm_code": "A203"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 200
    started = engineer.post(
        f"/api/incidents/{created.json()['incident_id']}/diagnoses",
        json={},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert started.status_code == 200
    execute(started.json()["job_id"])
    projection = engineer.get(f"/api/diagnoses/{started.json()['diagnosis_run_id']}")
    assert projection.status_code == 200
    body = projection.json()
    assert raw not in projection.text
    assert "SECRET-RAW-IDENTITY" not in projection.text
    assert body["report"]["evidence_sources"]
    assert all(item["citation_ids"] for item in body["report"]["possible_causes"])


def test_cross_role_cannot_read_media_evidence_or_job():
    from tests.acceptance.test_media_upload import png

    engineer = fixture_client("engineer")
    expert = fixture_client("expert")
    created = engineer.post(
        "/api/incidents",
        json={"raw_description": "A310，似乎漏气"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 200
    incident_id = created.json()["incident_id"]
    uploaded = engineer.post(
        f"/api/incidents/{incident_id}/media",
        files={"file": ("private.png", png(), "image/png")},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert uploaded.status_code == 200
    media_id, job_id = uploaded.json()["media_id"], uploaded.json()["job_id"]
    assert expert.get(f"/api/media/{media_id}/content").status_code == 404
    assert expert.get(f"/api/jobs/{job_id}").status_code == 404
    assert expert.get(f"/api/incidents/{incident_id}/evidence").status_code == 404
    assert expert.get(f"/api/media/{media_id}/frames/0/content").status_code == 404


def test_denied_provider_egress_is_explicit_and_sends_no_payload():
    profile = ProviderDataProfile(
        "jev",
        "https://api.typesafe.ai/v1/systemone",
        "profile-v1",
        "terms",
        datetime.now(UTC),
        True,
        ("SELF_AUTHORED_SIMULATION",),
    )
    grant = ProcessingGrant(
        policy_id="scope-test",
        version=1,
        origin="EXAM_SOURCE",
        egress="DENY",
        providers=("jev",),
        purposes=("retrieval",),
        basis="exam",
        expires_at=datetime.now(UTC),
        readable=True,
    )
    decision = authorize_egress((grant,), profile, "retrieval", {"state": {}})
    assert decision.decision == "SKIPPED_POLICY"
    assert decision.input_hash is None


def test_scoped_source_catalog_and_write_boundary():
    access_tests.test_baseline_alarm_and_safety_sources_are_scoped_and_no_case_reviewer_shortcut()
    access_tests.test_readable_event_does_not_allow_diagnosis_write()


def test_revoked_or_wrong_organization_resources_remain_hidden():
    access_tests.test_policy_denial_and_wrong_organization_remain_hidden()
