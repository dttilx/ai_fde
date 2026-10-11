from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.feedback.schemas import CaseReviewInput, DraftInput, RepairInput
from app.feedback.service import create_draft, publish_case, review_case, submit_repair
from app.shared.auth_context import ActorContext, current_actor
from app.shared.db import get_db

router = APIRouter(prefix="/api")


@router.get("/case-drafts/{draft_id}")
def get_draft(
    draft_id: str,
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    from app.access.service import require_resource
    from app.feedback.models import CaseDraft, VerifiedCase
    from app.shared.errors import DomainError
    from app.shared.jobs.models import Job

    require_resource(db, actor, "CASE_DRAFT", draft_id)
    row = db.get(CaseDraft, draft_id)
    if row is None:
        raise DomainError("NOT_FOUND", 404)
    verified = db.scalar(select(VerifiedCase).where(VerifiedCase.draft_id == row.id))
    job = db.scalar(
        select(Job).where(
            Job.kind == "CASE_PUBLICATION",
            Job.payload["draft_id"].as_string() == row.id,
        ).order_by(Job.created_at.desc())
    )
    # The assigned reviewer sees the delegated draft, not the entire incident.
    return {
        "case_draft_id": row.id,
        "status": row.status,
        "payload": row.payload,
        "requested_scope": row.requested_scope,
        "approved_scope": row.approved_scope,
        "deidentification_status": row.deidentification_status,
        "review_note": row.review_note,
        "publication_status": verified.status if verified else "NOT_REQUESTED",
        "job": {"job_id": job.id, "status": job.status, "status_version": job.fence,
                "error_code": job.error_code} if job else None,
    }


@router.post("/incidents/{incident_id}/repair-outcomes")
def repair(
    incident_id: str,
    body: RepairInput,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    outcome = submit_repair(db, actor, incident_id, key, body)
    db.commit()
    return {"repair_outcome_id": outcome.id, "validation_status": outcome.validation_status}


@router.post("/repair-outcomes/{outcome_id}/case-draft")
def draft(
    outcome_id: str,
    body: DraftInput,
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    row = create_draft(db, actor, outcome_id, body)
    db.commit()
    return {"case_draft_id": row.id, "status": row.status}


@router.post("/case-drafts/{draft_id}/review")
def review(
    draft_id: str,
    body: CaseReviewInput,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    row = review_case(db, actor, draft_id, body)
    publication = None
    if body.publish_on_approval:
        if not key:
            from app.shared.errors import DomainError

            raise DomainError("PUBLICATION_IDEMPOTENCY_REQUIRED", 422)
        release, job = publish_case(db, actor, draft_id, key)
        publication = {"knowledge_release_id": release.id, "job_id": job.id}
    db.commit()
    return {
        "case_draft_id": row.id,
        "status": row.status,
        "reviewer_id": row.assigned_reviewer_id,
        "publication": publication,
    }


@router.post("/case-drafts/{draft_id}/publish")
def publish(
    draft_id: str,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    release, job = publish_case(db, actor, draft_id, key)
    db.commit()
    return {
        "draft_id": draft_id,
        "knowledge_release_id": release.id,
        "job_id": job.id,
        "status": "QUEUED",
    }
