"""Expert and case governance acceptance; no draft is treated as production knowledge."""

import asyncio
import time
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.feedback.models import VerifiedCase
from app.feedback.processing import publish_case_job
from app.shared.db import session_factory
from app.shared.jobs.executor import ExecutorRegistry
from app.shared.jobs.models import Job
from app.shared.jobs.worker import Worker
from tests.acceptance.test_a203 import create
from tests.acceptance.test_resource_access import fixture_client


def run_case_publication(job_id: str) -> None:
    registry = ExecutorRegistry()
    registry.register("CASE_PUBLICATION", publish_case_job)
    worker = Worker(registry, timeout=30)
    for _ in range(20):
        with session_factory()() as db:
            job = db.get(Job, job_id)
            if job and job.status in {"SUCCEEDED", "FAILED", "TIMED_OUT"}:
                assert job.status == "SUCCEEDED", job.error_code
                return
        if not asyncio.run(worker.run_once()):
            # The application worker may already own this Job during an
            # integration run; wait for it instead of treating no local work
            # as a publication failure.
            time.sleep(0.05)
    raise AssertionError("case publication job not processed")


@pytest.mark.parametrize("retry_failed", [False, True])
def test_approve_publish_is_role_bound_idempotent_and_worker_completed(retry_failed):
    engineer, started = create()
    run_id = started["diagnosis_run_id"]
    report = engineer.get(f"/api/diagnoses/{run_id}").json()["report"]
    with session_factory()() as db:
        from app.access.models import QualificationGrant, User
        from app.diagnosis.models import DiagnosisRun
        from app.incidents.models import Evidence

        run = db.get(DiagnosisRun, run_id)
        user = db.scalar(select(User).where(User.username == "engineer"))
        reviewer_user = db.scalar(select(User).where(User.username == "reviewer"))
        grant = db.scalar(
            select(QualificationGrant).where(
                QualificationGrant.user_id == user.id,
                QualificationGrant.scope == "APX-240",
                QualificationGrant.active.is_(True),
            )
        )
        evidence = Evidence(
            incident_id=run.incident_id,
            evidence_key="repair-confirmation",
            state="CONFIRMED",
            source="FORM",
            value={"value": "现场维修记录"},
            reviewer_id=user.id,
        )
        db.add(evidence)
        db.commit()
        evidence_id, incident_id, executor_id = evidence.id, run.incident_id, user.id
    repair = engineer.post(
        f"/api/incidents/{incident_id}/repair-outcomes",
        json={
            "diagnosis_run_id": run_id,
            "report_version_id": report["report_version_id"],
            "executor_id": executor_id,
            "confirmed_root_cause": "维修记录确认加热回路开路",
            "confirmation_ref": "WO-240-042",
            "repair_action": "更换并复核加热回路",
            "repair_evidence_ids": [evidence_id],
            "qualification_refs": [grant.id],
            "restart_validation": "PASSED",
            "restart_evidence_ids": [evidence_id],
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert repair.status_code == 200, repair.text
    draft = engineer.post(
        f"/api/repair-outcomes/{repair.json()['repair_outcome_id']}/case-draft",
        json={
            "assigned_reviewer_id": reviewer_user.id,
            "requested_scope": {"reader_user_ids": [user.id]},
        },
    )
    assert draft.status_code == 200, draft.text
    reviewer = fixture_client("reviewer")
    draft_id = draft.json()["case_draft_id"]
    readable = reviewer.get(f"/api/case-drafts/{draft_id}")
    assert readable.status_code == 200, readable.text
    assert readable.json()["status"] == "DRAFT"
    assert engineer.get(f"/api/case-drafts/{draft_id}").status_code == 404
    assert fixture_client("expert").post(
        f"/api/case-drafts/{draft_id}/review",
        json={
            "decision": "APPROVE",
            "note": "专家不能代替案例审核",
            "deidentification_status": "PASSED",
            "approved_scope": {"reader_user_ids": [user.id]},
        },
    ).status_code == 403
    broader = reviewer.post(
        f"/api/case-drafts/{draft_id}/review",
        json={
            "decision": "APPROVE",
            "note": "不能扩大范围",
            "deidentification_status": "PASSED",
            "approved_scope": {"reader_user_ids": [reviewer_user.id]},
        },
    )
    assert broader.status_code == 422
    review_request = reviewer.post(
        f"/api/case-drafts/{draft_id}/review",
        json={
            "decision": "APPROVE",
            "note": "已核对维修证据",
            "deidentification_status": "PASSED",
            "approved_scope": {"reader_user_ids": [user.id]},
            "publish_on_approval": retry_failed,
        },
        headers={"Idempotency-Key": uuid4().hex} if retry_failed else {},
    )
    assert review_request.status_code == 200, review_request.text
    if retry_failed:
        job_id = review_request.json()["publication"]["job_id"]
    else:
        published = reviewer.post(
            f"/api/case-drafts/{draft_id}/publish",
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert published.status_code == 200, published.text
        job_id = published.json()["job_id"]
    if retry_failed:
        registry = ExecutorRegistry()

        async def failed_transport(ticket):
            raise RuntimeError("simulated publication transport failure")

        registry.register("CASE_PUBLICATION", failed_transport)
        assert asyncio.run(Worker(registry).run_once())
        status = reviewer.get(f"/api/jobs/{job_id}")
        assert status.status_code == 200, status.text
        assert status.json()["status"] == "FAILED"
        with session_factory()() as db:
            row = db.scalar(select(VerifiedCase).where(VerifiedCase.draft_id == draft_id))
            assert row.status == "APPROVED_UNPUBLISHED"
        headers = {"Idempotency-Key": uuid4().hex}
        body = {"expected_status_version": status.json()["status_version"]}
        assert engineer.post(
            f"/api/jobs/{job_id}/retry", json=body, headers=headers
        ).status_code == 403
        retried = reviewer.post(f"/api/jobs/{job_id}/retry", json=body, headers=headers)
        assert retried.status_code == 200, retried.text
        assert retried.json()["status"] == "RETRY_WAIT"
        assert reviewer.post(
            f"/api/jobs/{job_id}/retry", json=body, headers=headers
        ).status_code == 409
    time.sleep(0.05)
    run_case_publication(job_id)
    with session_factory()() as db:
        from app.access.models import User
        from app.access.resource_policy import authorized_source_ids
        from app.knowledge.models import SourceRecord
        from app.shared.auth_context import ActorContext

        row = db.scalar(select(VerifiedCase).where(VerifiedCase.draft_id == draft_id))
        assert row is not None and row.status == "PUBLISHED"
        source = db.scalar(
            select(SourceRecord).where(SourceRecord.release_id == row.knowledge_release_id)
        )
        user = db.scalar(select(User).where(User.username == "engineer"))
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        assert source.id in authorized_source_ids(db, actor)
    assert reviewer.post(
        f"/api/case-drafts/{draft_id}/publish",
        headers={"Idempotency-Key": uuid4().hex},
    ).status_code == 409


def test_incomplete_repair_is_retained_unverified_and_cannot_create_draft():
    engineer, started = create()
    run_id = started["diagnosis_run_id"]
    state = engineer.get(f"/api/diagnoses/{run_id}").json()
    outcome = engineer.post(
        f"/api/incidents/{state['incident_id']}/repair-outcomes",
        json={
            "diagnosis_run_id": run_id,
            "report_version_id": state["report"]["report_version_id"],
            "repair_action": "现场观察后暂不维修",
            "restart_validation": "UNKNOWN",
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert outcome.status_code == 200
    assert outcome.json()["validation_status"] == "UNVERIFIED"
    assert engineer.post(
        f"/api/repair-outcomes/{outcome.json()['repair_outcome_id']}/case-draft",
        json={"assigned_reviewer_id": "missing", "requested_scope": {"reader_user_ids": []}},
    ).status_code == 422
    assert fixture_client("reviewer").post(
        f"/api/incidents/{state['incident_id']}/repair-outcomes",
        json={
            "diagnosis_run_id": run_id,
            "report_version_id": state["report"]["report_version_id"],
        },
        headers={"Idempotency-Key": uuid4().hex},
    ).status_code == 403


def test_expert_revision_appends_version_and_keeps_ai_report():
    from sqlalchemy import select

    from app.access.models import PolicyBinding, ResourceGrant, User
    from app.diagnosis.models import PendingHumanAction, ReportVersion

    engineer, started = create()
    run_id = started["diagnosis_run_id"]
    original = engineer.get(f"/api/diagnoses/{run_id}").json()
    with session_factory()() as db:
        from app.diagnosis.models import DiagnosisRun, ReportVersion

        baseline_count = len(
            db.scalars(
                select(ReportVersion).where(
                    ReportVersion.run_id == db.get(DiagnosisRun, run_id).id
                )
            ).all()
        )
    with session_factory()() as db, db.begin():
        from app.diagnosis.models import DiagnosisRun

        run = db.get(DiagnosisRun, run_id)
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
        action = PendingHumanAction(
            run_id=run.id,
            snapshot_hash=run.snapshot_id,
            kind="EXPERT",
            reasons=["证据冲突待专家修订"],
            assigned_actor_id=expert.id,
        )
        db.add(action)
        db.flush()
        action_id = action.id
    expert_client = fixture_client("expert")
    opened = expert_client.post(
        f"/api/diagnoses/{run_id}/expert-reviews",
        json={"pending_action_id": action_id, "reason": "核对当前报告"},
    )
    assert opened.status_code == 200, opened.text
    revised = expert_client.post(
        f"/api/expert-reviews/{opened.json()['expert_review_id']}/revision",
        json={
            "resolution": "保留可能原因表述，补充授权复核要求",
            "evidence_refs": ["H02"],
            "report_version_id": original["report"]["report_version_id"],
        },
    )
    assert revised.status_code == 200, revised.text
    with session_factory()() as db:
        versions = db.scalars(select(ReportVersion).where(ReportVersion.run_id == run_id)).all()
        assert len(versions) == baseline_count + 1
        assert (
            db.get(ReportVersion, original["report"]["report_version_id"]).content_hash
            == original["report_hash"]
        )
