import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, QualificationGrant, ResourceGrant, User
from app.access.service import require_resource
from app.diagnosis.models import DiagnosisRun, ReportVersion
from app.feedback.models import CaseDraft, RepairOutcome, VerifiedCase
from app.feedback.schemas import CaseReviewInput, DraftInput, RepairInput
from app.incidents.models import Evidence, EvidenceSnapshot
from app.knowledge.models import KnowledgeRelease, SourceRecord
from app.shared.audit import AuditRecord
from app.shared.auth_context import ActorContext
from app.shared.errors import DomainError
from app.shared.jobs.models import Job
from app.shared.jobs.service import create_job
from app.shared.versioning import content_hash


def submit_repair(
    db: Session, actor: ActorContext, incident_id: str, key: str, body: RepairInput
) -> RepairOutcome:
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    require_resource(db, actor, "INCIDENT", incident_id, write=True)
    existing = db.scalar(select(RepairOutcome).where(RepairOutcome.idempotency_key == key))
    if existing:
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    run = db.get(DiagnosisRun, body.diagnosis_run_id)
    report = db.get(ReportVersion, body.report_version_id)
    if run is None or report is None or run.incident_id != incident_id or report.run_id != run.id:
        raise DomainError("REPAIR_LINEAGE_INVALID", 409)
    complete = bool(
        body.confirmed_root_cause
        and body.confirmation_ref
        and body.repair_action
        and body.executor_id
        and body.repair_evidence_ids
        and body.restart_validation == "PASSED"
        and body.restart_evidence_ids
        and body.qualification_refs
    )
    executor = db.get(User, body.executor_id) if body.executor_id else None
    if body.executor_id and executor is None:
        raise DomainError("EXECUTOR_QUALIFICATION_MISSING", 422)
    if body.qualification_refs and executor is None:
        raise DomainError("EXECUTOR_QUALIFICATION_MISSING", 422)
    if executor is not None and not executor.enabled:
        raise DomainError("EXECUTOR_QUALIFICATION_MISSING", 422)
    if body.qualification_refs:
        valid_grants = set(
            db.scalars(
                select(QualificationGrant.id).where(
                    QualificationGrant.id.in_(body.qualification_refs),
                    QualificationGrant.user_id == body.executor_id,
                    QualificationGrant.scope == "APX-240",
                    QualificationGrant.active.is_(True),
                    QualificationGrant.expires_at > datetime.now(UTC),
                    QualificationGrant.basis != "",
                )
            ).all()
        )
        if valid_grants != set(body.qualification_refs):
            raise DomainError("EXECUTOR_QUALIFICATION_MISSING", 422)
    evidence_ids = set(body.repair_evidence_ids + body.restart_evidence_ids)
    if evidence_ids:
        rows = db.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids))).all()
        if len(rows) != len(evidence_ids) or any(
            row.incident_id != incident_id or row.state not in {"CONFIRMED", "CORRECTED"}
            for row in rows
        ):
            raise DomainError("REPAIR_EVIDENCE_INVALID", 422)
        from app.evidence.policy import require_evidence_read

        for row in rows:
            require_evidence_read(db, actor, row)
    outcome = RepairOutcome(
        incident_id=incident_id,
        diagnosis_run_id=run.id,
        report_version_id=report.id,
        submitted_by=actor.id,
        executor_id=body.executor_id,
        confirmed_root_cause=body.confirmed_root_cause,
        confirmation_ref=body.confirmation_ref,
        repair_action=body.repair_action,
        repair_evidence_ids=body.repair_evidence_ids,
        qualification_refs=body.qualification_refs,
        restart_validation=body.restart_validation,
        restart_evidence_ids=body.restart_evidence_ids,
        validation_status="READY_FOR_REVIEW" if complete else "UNVERIFIED",
        idempotency_key=key,
    )
    db.add(outcome)
    db.flush()
    return outcome


def create_draft(db: Session, actor: ActorContext, outcome_id: str, body: DraftInput) -> CaseDraft:
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    outcome = db.get(RepairOutcome, outcome_id)
    if outcome is None or outcome.validation_status != "READY_FOR_REVIEW":
        raise DomainError("REPAIR_OUTCOME_INCOMPLETE", 422)
    require_resource(db, actor, "INCIDENT", outcome.incident_id, write=True)
    reviewer = db.get(User, body.assigned_reviewer_id)
    if (
        not reviewer
        or not reviewer.enabled
        or "CASE_REVIEWER" not in reviewer.roles
        or reviewer.organization_id != actor.organization_id
    ):
        raise DomainError("CASE_REVIEWER_INVALID", 422)
    if reviewer.id in {outcome.submitted_by, outcome.executor_id}:
        raise DomainError("CASE_SELF_REVIEW_FORBIDDEN", 403)
    policy = db.scalar(
        select(PolicyBinding).where(
            PolicyBinding.resource_type == "INCIDENT",
            PolicyBinding.resource_id == outcome.incident_id,
        )
    )
    readers = set(body.requested_scope.reader_user_ids)
    if not readers or not policy or not readers.issubset(policy.readable_by):
        raise DomainError("CASE_SCOPE_INVALID", 422)
    if db.scalar(select(CaseDraft).where(CaseDraft.repair_outcome_id == outcome_id)):
        raise DomainError("CASE_DRAFT_EXISTS", 409)
    draft = CaseDraft(
        repair_outcome_id=outcome_id,
        payload={
            "confirmed_root_cause": outcome.confirmed_root_cause,
            "repair_action": outcome.repair_action,
            "restart_validation": outcome.restart_validation,
        },
        requested_scope=body.requested_scope.model_dump(),
        assigned_reviewer_id=reviewer.id,
    )
    db.add(draft)
    db.flush()
    db.add(
        PolicyBinding(
            resource_type="CASE_DRAFT",
            resource_id=draft.id,
            classification="FIELD_RECORD",
            origin=policy.origin,
            readable_by=[reviewer.id],
            egress="DENY",
        )
    )
    db.add(
        ResourceGrant(
            user_id=reviewer.id,
            resource_type="CASE_DRAFT",
            resource_id=draft.id,
            permission="WRITE",
        )
    )
    return draft


def review_case(db: Session, actor: ActorContext, draft_id: str, body: CaseReviewInput):
    actor.require_role("CASE_REVIEWER")
    require_resource(db, actor, "CASE_DRAFT", draft_id, write=True)
    draft = db.get(CaseDraft, draft_id)
    if draft is None or draft.status not in {"DRAFT", "IN_REVIEW"}:
        raise DomainError("CASE_REVIEW_INVALID", 409)
    if draft.assigned_reviewer_id and draft.assigned_reviewer_id != actor.id:
        raise DomainError("CASE_REVIEWER_NOT_ASSIGNED", 403)
    outcome = db.get(RepairOutcome, draft.repair_outcome_id)
    if outcome is None or actor.id in {outcome.submitted_by, outcome.executor_id}:
        raise DomainError("CASE_SELF_REVIEW_FORBIDDEN", 403)
    draft.status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
    draft.assigned_reviewer_id = actor.id
    draft.review_note = body.note
    draft.deidentification_status = body.deidentification_status
    if body.decision == "APPROVE":
        requested = set(draft.requested_scope.get("reader_user_ids", []))
        approved = set(body.approved_scope.reader_user_ids)
        if not approved or not approved.issubset(requested):
            raise DomainError("CASE_SCOPE_INVALID", 422)
        draft.approved_scope = body.approved_scope.model_dump()
    if body.decision == "APPROVE" and body.deidentification_status != "PASSED":
        raise DomainError("DEIDENTIFICATION_REQUIRED", 422)
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="CASE_REVIEW",
            resource_id=draft.id,
            details={
                "decision": body.decision,
                "approval_hash": content_hash([draft.payload, draft.approved_scope]),
                "deidentification": body.deidentification_status,
            },
        )
    )
    db.flush()
    return draft


def publish_case(db: Session, actor: ActorContext, draft_id: str, key: str):
    actor.require_role("CASE_REVIEWER")
    require_resource(db, actor, "CASE_DRAFT", draft_id, write=True)
    draft = db.get(CaseDraft, draft_id, with_for_update=True)
    if draft is None or draft.status != "APPROVED" or draft.assigned_reviewer_id != actor.id:
        raise DomainError("CASE_PUBLICATION_NOT_APPROVED", 409)
    outcome = db.get(RepairOutcome, draft.repair_outcome_id)
    if outcome is None:
        raise DomainError("CASE_LINEAGE_INVALID", 409)
    existing_case = db.scalar(select(VerifiedCase).where(VerifiedCase.draft_id == draft_id))
    if existing_case:
        existing_release = db.get(KnowledgeRelease, existing_case.knowledge_release_id)
        existing_job = db.scalar(
            select(Job).where(
                Job.resource_id == outcome.incident_id,
                Job.kind == "CASE_PUBLICATION",
                Job.idempotency_key == key,
            )
        )
        if existing_case.status == "APPROVED_UNPUBLISHED" and existing_release and existing_job:
            return existing_release, existing_job
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    # Publication is scoped by the reviewer assignment and the approved draft.
    # Case reviewers do not receive broad incident read grants merely to publish.
    source_text = json.dumps(draft.payload, ensure_ascii=False, sort_keys=True)
    run = db.get(DiagnosisRun, outcome.diagnosis_run_id)
    snapshot = db.get(EvidenceSnapshot, run.snapshot_id) if run else None
    alarm_code = snapshot.facts.get("alarm_code", "UNKNOWN") if snapshot else "UNKNOWN"
    release = KnowledgeRelease(
        release_key=f"verified-case-{draft.id}",
        source_checksum=content_hash(source_text),
        config={"mode": "VERIFIED_CASE", "scope": draft.approved_scope or draft.requested_scope},
    )
    db.add(release)
    db.flush()
    source = SourceRecord(
        release_id=release.id,
        source_key=f"CASE-{draft.id}",
        collection="APPROVED_CASE",
        content=source_text,
        locator={"case_draft_id": draft.id, "page": 1, "section": "已审核维修案例"},
        checksum=hashlib.sha256(source_text.encode()).hexdigest(),
        metadata_fields={
            # Retrieval additionally requires VerifiedCase.status=PUBLISHED;
            # this immutable source row is never edited by the worker.
            "status": "VERIFIED",
            "model": "APX-240",
            "reviewer_id": actor.id,
            "publication_id": release.id,
            "alarm_code": alarm_code,
        },
    )
    db.add(source)
    db.flush()
    incident_policy = db.scalar(
        select(PolicyBinding).where(
            PolicyBinding.resource_type == "INCIDENT",
            PolicyBinding.resource_id == outcome.incident_id,
        )
    )
    readers = db.scalars(select(User).where(User.enabled.is_(True))).all()
    incident_readers = set(incident_policy.readable_by if incident_policy else [])
    approved_readers = set((draft.approved_scope or {}).get("reader_user_ids", []))
    if not approved_readers or not approved_readers.issubset(incident_readers):
        raise DomainError("CASE_SCOPE_INVALID", 422)
    readers = [user for user in readers if user.id in approved_readers]
    db.add(
        PolicyBinding(
            resource_type="SOURCE",
            resource_id=source.id,
            classification="FIELD_RECORD",
            origin=incident_policy.origin,
            readable_by=[user.id for user in readers],
            egress="DENY",
            basis=f"CASE_REVIEW:{draft.id}",
        )
    )
    for user in readers:
        db.add(ResourceGrant(user_id=user.id, resource_type="SOURCE", resource_id=source.id))
    job = create_job(
        db,
        outcome.incident_id,
        actor.id,
        "CASE_PUBLICATION",
        key,
        {
            "draft_id": draft.id,
            "release_id": release.id,
            "actor_version": actor.auth_version,
            "approval_hash": content_hash([draft.payload, draft.approved_scope]),
        },
    )
    db.add(
        VerifiedCase(
            draft_id=draft.id,
            knowledge_release_id=release.id,
            status="APPROVED_UNPUBLISHED",
            approved_by=actor.id,
            published_at=None,
        )
    )
    db.flush()
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="CASE_PUBLICATION_QUEUED",
            resource_id=draft.id,
            details={
                "job_id": job.id,
                "release_id": release.id,
                "approval_hash": content_hash([draft.payload, draft.approved_scope]),
            },
        )
    )
    return release, job
