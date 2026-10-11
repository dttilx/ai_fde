"""Append a non-actionable report after a late citation conflict."""

from copy import deepcopy

from app.access.models import new_id
from app.diagnosis.models import ReportVersion
from app.diagnosis.release_models import ReportReleaseDecision
from app.diagnosis.report import validate_report
from app.shared.errors import DomainError
from app.shared.versioning import content_hash


def withhold_conflict(db, run, draft, assessment_ids):
    safe_ids = [
        c["citation_id"] for c in draft.payload["evidence_sources"] if c["source_ref"] == "SAFE-05"
    ]
    if not safe_ids:
        raise DomainError("SAFETY_CITATION_MISSING", 409)
    if draft.payload["publication_status"] == "WITHHELD":
        return draft
    payload = deepcopy(draft.payload)
    action = deepcopy(draft.payload["stop_conditions"][-1])
    action.update(
        instruction_id=new_id(),
        order=1,
        text="引用与候选结论存在冲突，停止进一步排查并转交专家核实。",
        citation_ids=safe_ids,
        evidence_ids=[],
        alarm_step_ref=None,
        required_qualification=[],
        policy_reference_ids=[],
        execution_boundary="OBSERVATION_ONLY",
    )
    reason = {**action, "instruction_id": new_id()}
    payload.update(
        report_version_id=new_id(),
        release_decision_id=new_id(),
        validation_check_ids=[],
        claim_review_ids=[],
        reviewer_ids=[],
        status="CONFLICT_BLOCKED",
        publication_status="WITHHELD",
        release_mode="PENDING_REVIEW",
        safety_blocked=True,
        escalate_expert=True,
        possible_causes=[],
        check_sequence=[],
        safety_preconditions=[],
        immediate_safety_actions=[action],
        escalation_reasons=[reason],
    )
    payload["limitations"].append("原草稿已停止使用，专家处置不代表批准设备操作或复机。")
    validate_report(payload)
    report_hash = content_hash(payload)
    report = ReportVersion(
        id=payload["report_version_id"],
        run_id=run.id,
        parent_id=draft.id,
        payload=payload,
        content_hash=report_hash,
        manifest={
            **draft.manifest,
            "withheld_parent_hash": draft.content_hash,
            "claim_support_assessment_ids": assessment_ids,
        },
    )
    db.add(report)
    db.add(
        ReportReleaseDecision(
            id=payload["release_decision_id"],
            report_hash=report_hash,
            mode="PENDING_REVIEW",
            payload={"reason": "CITATION_CONFLICT", "parent_hash": draft.content_hash},
        )
    )
    run.report_version_id = report.id
    db.flush()
    return report
