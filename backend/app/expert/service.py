from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import new_id
from app.access.service import require_resource
from app.diagnosis.models import DiagnosisRun, PendingHumanAction, ReportVersion
from app.expert.models import ExpertReview
from app.expert.schemas import ExpertOpen, ExpertRevision
from app.shared.auth_context import ActorContext
from app.shared.errors import DomainError
from app.shared.versioning import content_hash


def open_review(db: Session, actor: ActorContext, run_id: str, body: ExpertOpen) -> ExpertReview:
    actor.require_role("EXPERT")
    run = db.get(DiagnosisRun, run_id)
    if run is None:
        raise DomainError("NOT_FOUND", 404)
    require_resource(db, actor, "INCIDENT", run.incident_id, write=True)
    action = db.get(PendingHumanAction, body.pending_action_id)
    if action is None or action.run_id != run_id or action.kind not in {"EXPERT", "HIGH_RISK"}:
        raise DomainError("PENDING_ACTION_INVALID", 409)
    if action.assigned_actor_id and action.assigned_actor_id != actor.id:
        raise DomainError("EXPERT_REVIEW_FORBIDDEN", 403)
    existing = db.scalar(
        select(ExpertReview).where(
            ExpertReview.pending_action_id == action.id,
            ExpertReview.status.in_(("OPEN", "REVISED")),
        )
    )
    if existing:
        return existing
    review = ExpertReview(
        run_id=run_id,
        pending_action_id=action.id,
        assigned_actor_id=actor.id,
        reason=body.reason,
        status="OPEN",
    )
    db.add(review)
    db.flush()
    return review


def revise(db: Session, actor: ActorContext, review_id: str, body: ExpertRevision) -> ExpertReview:
    actor.require_role("EXPERT")
    review = db.get(ExpertReview, review_id)
    if review is None or review.assigned_actor_id != actor.id or review.status != "OPEN":
        raise DomainError("EXPERT_REVIEW_FORBIDDEN", 403)
    report = db.get(ReportVersion, body.report_version_id)
    run = db.get(DiagnosisRun, review.run_id)
    if report is None or run is None or report.run_id != run.id:
        raise DomainError("REPORT_NOT_FOUND", 404)
    require_resource(db, actor, "INCIDENT", run.incident_id, write=True)
    revised_id = new_id()
    payload = {**report.payload, "report_version_id": revised_id}
    # A revision is a separate immutable report version; the AI row is untouched.
    revised = ReportVersion(
        id=revised_id,
        run_id=run.id,
        parent_id=report.id,
        payload=payload,
        manifest={
            **report.manifest,
            "expert_resolution": body.resolution,
            "expert_evidence_refs": list(body.evidence_refs),
            "expert_reviewer_id": actor.id,
        },
        content_hash=content_hash(payload),
        kind="EXPERT",
    )
    db.add(revised)
    review.report_version_ids = [*review.report_version_ids, report.id, revised.id]
    review.resolution, review.evidence_refs = body.resolution, list(body.evidence_refs)
    review.status, review.closed_by, review.closed_at = "REVISED", actor.id, datetime.now(UTC)
    db.flush()
    return review
