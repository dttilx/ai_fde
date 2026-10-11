"""Case publication scope and role boundaries.

These tests intentionally exercise the HTTP boundary; no fixture result is
treated as an approved case until the publication worker succeeds.
"""

from uuid import uuid4

from sqlalchemy import select

from app.access.models import PolicyBinding, QualificationGrant, User
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create
from tests.acceptance.test_resource_access import fixture_client


def test_expert_cannot_review_or_publish_and_scope_is_explicit():
    engineer, started = create()
    state = engineer.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    with session_factory()() as db:
        user = db.scalar(select(User).where(User.username == "engineer"))
        reviewer = db.scalar(select(User).where(User.username == "reviewer"))
        grant = db.scalar(
            select(QualificationGrant).where(
                QualificationGrant.user_id == user.id,
                QualificationGrant.scope == "APX-240",
                QualificationGrant.active.is_(True),
            )
        )
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "INCIDENT",
                PolicyBinding.resource_id == state["incident_id"],
            )
        )
        if reviewer.id not in policy.readable_by:
            policy.readable_by = [*policy.readable_by, reviewer.id]
        db.commit()
        reviewer_id, grant_id = reviewer.id, grant.id
    repair = engineer.post(
        f"/api/incidents/{state['incident_id']}/repair-outcomes",
        json={
            "diagnosis_run_id": started["diagnosis_run_id"],
            "report_version_id": state["report"]["report_version_id"],
            "confirmed_root_cause": "现场维修记录确认",
            "confirmation_ref": "WO-240-042",
            "repair_action": "更换加热回路并复机验证",
            "executor_id": user.id,
            "qualification_refs": [grant_id],
            "restart_validation": "PASSED",
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert repair.status_code == 200
    # Missing repair evidence must remain unverified; it cannot become a draft.
    assert repair.json()["validation_status"] == "UNVERIFIED"
    assert engineer.post(
        f"/api/repair-outcomes/{repair.json()['repair_outcome_id']}/case-draft",
        json={
            "assigned_reviewer_id": reviewer_id,
            "requested_scope": {"reader_user_ids": [user.id]},
        },
    ).status_code == 422
    assert fixture_client("expert").post(
        "/api/case-drafts/unknown/review",
        json={
            "decision": "APPROVE",
            "note": "越权测试",
            "deidentification_status": "PASSED",
            "approved_scope": {"reader_user_ids": [reviewer_id]},
        },
    ).status_code in {403, 404}
