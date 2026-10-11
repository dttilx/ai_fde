from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant, User
from app.diagnosis.models import DiagnosisRun, PendingHumanAction
from app.incidents.models import Evidence, EvidenceSnapshot
from app.safety.checks import ACTIONS, check_preconditions
from app.shared.auth_context import ActorContext
from app.shared.config import settings
from app.shared.db import session_factory
from app.shared.versioning import content_hash
from tests.acceptance.test_a203 import create, execute
from tests.acceptance.test_resource_access import fixture_client


@pytest.fixture
def stopped():
    engineer, started = create(description="A203，现场出现烟雾和焦味")
    admin = create_engine(settings().migration_database_url.get_secret_value())
    with Session(admin) as db, db.begin():
        run = db.get(DiagnosisRun, started["diagnosis_run_id"])
        expert = db.scalar(select(User).where(User.username == "expert"))
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "INCIDENT",
                PolicyBinding.resource_id == run.incident_id,
            )
        )
        policy.readable_by = [*policy.readable_by, expert.id]
        db.add(
            ResourceGrant(
                user_id=expert.id,
                resource_type="INCIDENT",
                resource_id=run.incident_id,
                permission="WRITE",
            )
        )
        snapshot = db.get(EvidenceSnapshot, run.snapshot_id)
        for source_id in run.source_scope:
            source_policy = db.scalar(
                select(PolicyBinding).where(
                    PolicyBinding.resource_type == "SOURCE",
                    PolicyBinding.resource_id == source_id,
                )
            )
            if source_policy and expert.id not in source_policy.readable_by:
                source_policy.readable_by = [*source_policy.readable_by, expert.id]
                db.add(
                    ResourceGrant(
                        user_id=expert.id,
                        resource_type="SOURCE",
                        resource_id=source_id,
                        permission="READ",
                    )
                )
        if snapshot:
            for evidence_id in snapshot.evidence_ids:
                evidence_policy = db.scalar(
                    select(PolicyBinding).where(
                        PolicyBinding.resource_type == "EVIDENCE",
                        PolicyBinding.resource_id == evidence_id,
                    )
                )
                if evidence_policy and expert.id not in evidence_policy.readable_by:
                    evidence_policy.readable_by = [*evidence_policy.readable_by, expert.id]
                    db.add(
                        ResourceGrant(
                            user_id=expert.id,
                            resource_type="EVIDENCE",
                            resource_id=evidence_id,
                            permission="READ",
                        )
                    )
        incident_id, expert_id = run.incident_id, expert.id
    try:
        yield engineer, fixture_client("expert"), started, incident_id, admin, expert_id
    finally:
        admin.dispose()


def disposition(client, run_id):
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    return {
        "type": "EXPERT",
        "interrupt_id": cp["interrupt_id"],
        "expected_checkpoint_version": cp["checkpoint_version"],
        "idempotency_key": uuid4().hex,
        "resolution": "已停机并转交授权专家，未批准试运行。",
    }


def test_high_risk_notice_is_cited_and_expert_acknowledgement_never_retrieves(stopped):
    engineer, expert, started, incident_id, _, _ = stopped
    run_id = started["diagnosis_run_id"]
    notice = engineer.get(f"/api/incidents/{incident_id}").json()["immediate_safety_notice"]
    assert notice["safety_blocked"]
    assert notice["citations"][0]["source_ref"] == "SAFE-01"
    assert notice["citations"][0]["page"] == 3
    before = engineer.get(f"/api/jobs/{started['job_id']}").json()
    assert before["status"] == "SUCCEEDED" and before["result_kind"] == "PAUSED"
    body = disposition(expert, run_id)
    assert engineer.post(f"/api/diagnoses/{run_id}/resume", json=body).status_code == 403
    accepted = expert.post(f"/api/diagnoses/{run_id}/resume", json=body)
    assert accepted.status_code == 200, accepted.text
    execute(accepted.json()["job_id"])
    result = expert.get(f"/api/diagnoses/{run_id}").json()
    assert result["state"] == "ESCALATED" and result["report"] is None
    assert "retrieve" not in [item["node"] for item in result["timeline"]]
    cp = expert.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert cp["interrupt_id"] is None and cp["counters"]["resumes"] == 1
    with session_factory()() as db:
        assert (
            len(
                db.scalars(
                    select(PendingHumanAction).where(PendingHumanAction.run_id == run_id)
                ).all()
            )
            == 1
        )


def test_revoked_expert_after_enqueue_cannot_commit_disposition(stopped):
    _, expert, started, _, admin, expert_id = stopped
    run_id = started["diagnosis_run_id"]
    response = expert.post(f"/api/diagnoses/{run_id}/resume", json=disposition(expert, run_id))
    assert response.status_code == 200
    with Session(admin) as db, db.begin():
        user = db.get(User, expert_id)
        user.enabled = False
        user.auth_version += 1
    try:
        with pytest.raises(AssertionError, match="EXECUTION_FAILED"):
            execute(response.json()["job_id"])
        with session_factory()() as db:
            run = db.get(DiagnosisRun, run_id)
            assert run.status == "FAILED" and run.failure_reason == "RESUME_ACTOR_REVOKED"
            assert run.report_version_id is None
    finally:
        with Session(admin) as db, db.begin():
            user = db.get(User, expert_id)
            user.enabled = True
            user.auth_version += 1


def test_new_danger_snapshot_requires_new_expert_disposition(stopped):
    _, expert, started, incident_id, _, _ = stopped
    run_id = started["diagnosis_run_id"]
    accepted = expert.post(f"/api/diagnoses/{run_id}/resume", json=disposition(expert, run_id))
    assert accepted.status_code == 200
    # Inject a newly confirmed observation while the continuation is queued.
    with session_factory()() as db, db.begin():
        run = db.get(DiagnosisRun, run_id)
        old = db.get(EvidenceSnapshot, run.snapshot_id)
        evidence = Evidence(
            incident_id=incident_id,
            evidence_key="loose_part",
            state="CONFIRMED",
            source="FORM",
            value={"value": True},
            reviewer_id=run.actor_id,
        )
        db.add(evidence)
        db.flush()
        facts, ids = {**old.facts, "loose_part": True}, [*old.evidence_ids, evidence.id]
        snapshot = EvidenceSnapshot(
            incident_id=incident_id,
            facts=facts,
            evidence_ids=ids,
            unknowns=old.unknowns,
            contradictions=old.contradictions,
            content_hash=content_hash([facts, ids, old.unknowns, old.contradictions]),
        )
        db.add(snapshot)
        db.flush()
        run.snapshot_id = snapshot.id
    execute(accepted.json()["job_id"])
    result = expert.get(f"/api/diagnoses/{run_id}").json()
    assert result["state"] == "WAITING_EXPERT" and result["report"] is None
    assert "retrieve" not in [row["node"] for row in result["timeline"]]
    with session_factory()() as db:
        assert (
            len(
                db.scalars(
                    select(PendingHumanAction).where(PendingHumanAction.run_id == run_id)
                ).all()
            )
            == 2
        )


@pytest.mark.parametrize("action", ACTIONS)
def test_every_maintenance_precondition_is_sourced_and_never_device_permission(action):
    client = fixture_client("engineer")
    response = client.post(
        "/api/incidents",
        json={"raw_description": "设备停机待核实"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 200
    with session_factory()() as db:
        user = db.scalar(select(User).where(User.username == "engineer"))
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        checked = check_preconditions(db, actor, response.json()["incident_id"], action)
        assert checked["allows_device_operation"] is False
        assert checked["instructions"] and checked["citations"]
        assert {"SAFE-02", "SAFE-03", "SAFE-04"}.issubset(
            {row["source_ref"] for row in checked["citations"]}
        )
        if action == "PRESSURE_WORK":
            assert "泄压" in "".join(checked["instructions"])
