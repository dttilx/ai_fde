import re
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.access.models import PolicyBinding, ResourceGrant, User, new_id
from app.access.qualifications import qualification_records, qualifications
from app.diagnosis.citation_assessment import validate_citations
from app.diagnosis.models import Citation, DiagnosisRun, ReportVersion
from app.diagnosis.release_models import ReportReleaseDecision
from app.diagnosis.report import validate_report
from app.diagnosis.service import accessible_run
from app.incidents.models import EvidenceSnapshot
from app.knowledge.assessment_models import ClaimReview
from app.safety.service import evaluate
from app.shared.auth_context import ActorContext
from app.shared.db import require_record
from app.shared.errors import DomainError
from app.shared.versioning import content_hash


def material_claims(payload: dict) -> dict[str, dict]:
    result = {}
    for area in (
        "possible_causes",
        "manual_references",
        "safety_preconditions",
        "check_sequence",
        "stop_conditions",
        "immediate_safety_actions",
        "escalation_reasons",
    ):
        for index, item in enumerate(payload[area]):
            key = item.get("claim_id") or item.get("instruction_id") or f"{area}:{index}"
            if key in result:
                raise DomainError("DUPLICATE_REPORT_CLAIM", 409)
            result[key] = item
    return result


def required_review_qualifications(payload: dict) -> set[str]:
    return {
        qualification
        for item in material_claims(payload).values()
        for qualification in item.get("required_qualification", [])
    }


class ClaimDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    claim_hash: str
    decision: Literal["ACCEPT", "CORRECT", "REJECT"]
    note: str = Field(min_length=1, max_length=1000)
    verified_source_refs: list[str] = Field(min_length=1, max_length=20)
    correction: str | None = Field(default=None, min_length=1, max_length=1000)


class ReviewBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version_id: str
    report_hash: str
    decisions: list[ClaimDecision] = Field(min_length=1, max_length=20)


def review_binding(db, actor, run, report) -> dict:
    """Bind approval to the current evidence and all local authorization contributors."""
    from app.access.service import require_resource

    require_resource(db, actor, "INCIDENT", run.incident_id, write=True)
    snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
    if (
        snapshot.contradictions
        or snapshot.content_hash != report.manifest["evidence_snapshot_hash"]
    ):
        raise DomainError("REPORT_REVIEW_EVIDENCE_CHANGED", 409)
    validate_citations(db, actor, report.payload["evidence_sources"])
    source_ids = [
        require_record(db, Citation, cite["citation_id"]).source_id
        for cite in report.payload["evidence_sources"]
    ]
    policies = db.scalars(
        select(PolicyBinding).where(
            ((PolicyBinding.resource_type == "SOURCE") & PolicyBinding.resource_id.in_(source_ids))
            | (
                (PolicyBinding.resource_type == "INCIDENT")
                & (PolicyBinding.resource_id == run.incident_id)
            )
        )
    ).all()
    grants = db.scalars(
        select(ResourceGrant).where(
            ResourceGrant.user_id == actor.id,
            ((ResourceGrant.resource_type == "SOURCE") & ResourceGrant.resource_id.in_(source_ids))
            | (
                (ResourceGrant.resource_type == "INCIDENT")
                & (ResourceGrant.resource_id == run.incident_id)
            ),
            ResourceGrant.active.is_(True),
        )
    ).all()
    return {
        "actor_version": actor.auth_version,
        "evidence_snapshot_hash": snapshot.content_hash,
        "resource_grant_hash": content_hash(
            sorted(
                [
                    {"id": grant.id, "version": grant.version, "permission": grant.permission}
                    for grant in grants
                ],
                key=lambda item: item["id"],
            )
        ),
        "source_policy_hash": content_hash(
            sorted(
                [
                    {
                        column.name: getattr(policy, column.name).isoformat()
                        if hasattr(getattr(policy, column.name), "isoformat")
                        else getattr(policy, column.name)
                        for column in PolicyBinding.__table__.columns
                    }
                    for policy in policies
                ],
                key=lambda item: item["id"],
            )
        ),
        "qualification_hash": content_hash(
            sorted(
                [
                    {
                        "id": grant.id,
                        "qualification": grant.qualification,
                        "basis": grant.basis,
                        "expires_at": grant.expires_at.isoformat(),
                        "scope": grant.scope,
                    }
                    for grant in qualification_records(db, actor)
                ],
                key=lambda item: item["id"],
            )
        ),
    }


def accepted_reviews(db, report: ReportVersion, reviewer_id: str, ids: list[str]) -> bool:
    claims = material_claims(report.payload)
    if len(ids) != len(claims) or len(ids) != len(set(ids)):
        return False
    user = db.get(User, reviewer_id)
    if not user or not user.enabled:
        return False
    actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
    if not set(actor.roles).intersection({"FIELD_ENGINEER", "EXPERT"}):
        return False
    if not required_review_qualifications(report.payload).issubset(qualifications(db, actor)):
        return False
    try:
        run = accessible_run(db, actor, report.run_id)
        binding = review_binding(db, actor, run, report)
    except DomainError as exc:
        if exc.status in {403, 404} or exc.code == "REPORT_REVIEW_EVIDENCE_CHANGED":
            return False
        raise
    if db.scalar(
        select(ClaimReview.id).where(
            ClaimReview.report_id == report.id, ClaimReview.decision == "REJECT"
        )
    ):
        return False
    from app.diagnosis.claim_support import conflicting_claims

    if conflicting_claims(db, report):
        return False
    reviews = db.scalars(select(ClaimReview).where(ClaimReview.id.in_(ids))).all()
    return len(reviews) == len(ids) and set(claims) == {
        row.claim_id
        for row in reviews
        if row.report_id == report.id
        and row.report_hash == report.content_hash
        and row.actor_id == reviewer_id
        and row.decision == "ACCEPT"
        and row.claim_id in claims
        and row.claim_hash == content_hash(claims[row.claim_id])
        and row.payload.get("binding") == binding
    }


def submit_reviews(db, actor, run_id: str, body: ReviewBatch, key: str):
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    accessible_run(db, actor, run_id)
    run = db.get(DiagnosisRun, run_id, with_for_update=True, populate_existing=True)
    if not run or run.interrupt_type != "REPORT_REVIEW":
        raise DomainError("REPORT_NOT_AWAITING_REVIEW", 409)
    from app.access.service import require_resource

    require_resource(db, actor, "INCIDENT", run.incident_id, write=True)
    report = require_record(db, ReportVersion, run.report_version_id)
    if not required_review_qualifications(report.payload).issubset(qualifications(db, actor)):
        raise DomainError("QUALIFICATION_REQUIRED", 403)
    if report.id != body.report_version_id or report.content_hash != body.report_hash:
        raise DomainError("REPORT_REVIEW_STALE", 409)
    if any(
        row.payload.get("idempotency_key") == key
        for row in db.scalars(select(ClaimReview).where(ClaimReview.run_id == run.id))
    ):
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    binding = review_binding(db, actor, run, report)
    claims = material_claims(report.payload)
    from app.diagnosis.claim_support import conflicting_claims

    conflicts = conflicting_claims(db, report)
    if len({item.claim_id for item in body.decisions}) != len(body.decisions):
        raise DomainError("DUPLICATE_CLAIM", 409)
    corrected = deepcopy(report.payload)
    revised = material_claims(corrected)
    reviews = []
    for item in body.decisions:
        claim = claims.get(item.claim_id)
        if not claim or content_hash(claim) != item.claim_hash:
            raise DomainError("CLAIM_HASH_STALE", 409)
        if set(item.verified_source_refs) != set(claim["citation_ids"]):
            raise DomainError("CLAIM_SOURCE_MISMATCH", 409)
        if item.claim_id in conflicts:
            if item.decision == "ACCEPT":
                raise DomainError("CLAIM_CONFLICT_REQUIRES_RESOLUTION", 409)
            if item.decision == "CORRECT":
                actor.require_role("EXPERT")
        if item.decision == "CORRECT":
            if not item.correction:
                raise DomainError("CORRECTION_REQUIRED")
            safety = evaluate(item.correction, {}, qualifications(db, actor))
            if (
                safety.safety_blocked
                or any(word in item.correction for word in ("已确认根因", "确定根因", "批准复机"))
                or re.search(
                    r"(?:最终|确定|确认)(?:的)?根因(?:为|是|[:：])|根因(?:已经|已)?(?:确定|确认)|(?:可以|允许)复机",
                    item.correction,
                )
            ):
                raise DomainError("UNSAFE_OR_FINAL_CAUSE_CORRECTION", 409)
            target = revised[item.claim_id]
            target["cause" if "cause" in target else "text"] = item.correction
        elif item.correction:
            raise DomainError("UNEXPECTED_CORRECTION")
        row = ClaimReview(
            run_id=run.id,
            report_id=report.id,
            actor_id=actor.id,
            report_hash=report.content_hash,
            claim_id=item.claim_id,
            claim_hash=item.claim_hash,
            decision=item.decision,
            payload={**item.model_dump(), "idempotency_key": key, "binding": binding},
        )
        db.add(row)
        reviews.append(row)
    if any(item.decision == "CORRECT" for item in body.decisions):
        corrected.update(
            report_version_id=new_id(),
            release_decision_id=new_id(),
            validation_check_ids=[],
            claim_review_ids=[],
            reviewer_ids=[],
            release_mode="PENDING_REVIEW",
            publication_status="DRAFT",
            status="FINALIZING",
        )
        validate_report(corrected)
        changed_hash = content_hash(corrected)
        db.add(
            ReportVersion(
                id=corrected["report_version_id"],
                run_id=run.id,
                parent_id=report.id,
                payload=corrected,
                content_hash=changed_hash,
                manifest={
                    **report.manifest,
                    "human_corrected": True,
                    "correction_parent_hash": report.content_hash,
                },
            )
        )
        db.add(
            ReportReleaseDecision(
                id=corrected["release_decision_id"],
                report_hash=changed_hash,
                mode="PENDING_REVIEW",
                payload={"corrected_from": report.id},
            )
        )
        run.report_version_id = corrected["report_version_id"]
    db.flush()
    from app.diagnosis.citation_assessment import record_claim_sets

    record_claim_sets(db, actor, run, require_record(db, ReportVersion, run.report_version_id))
    return {"review_ids": [row.id for row in reviews], "report_version_id": run.report_version_id}
