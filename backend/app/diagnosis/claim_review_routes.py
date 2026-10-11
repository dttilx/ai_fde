from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.diagnosis.citation_assessment import assess_claim_sets
from app.diagnosis.claim_review import ClaimDecision, ReviewBatch, submit_reviews
from app.diagnosis.models import ReportVersion
from app.diagnosis.service import accessible_run
from app.shared.auth_context import ActorContext, current_actor
from app.shared.db import get_db, require_record

router = APIRouter(prefix="/api/diagnoses")


@router.get("/{run_id}/citation-assessments")
def assessments(
    run_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)
):
    run = accessible_run(db, actor, run_id)
    if not run.report_version_id:
        return {"diagnosis_run_id": run.id, "assessments": [], "status": "NO_REPORT"}
    report = require_record(db, ReportVersion, run.report_version_id)
    return {
        "diagnosis_run_id": run.id,
        "report_version_id": report.id,
        "assessments": assess_claim_sets(db, actor, run, report),
    }


@router.post("/{run_id}/claim-reviews/batch")
def batch(
    run_id: str,
    body: ReviewBatch,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    result = submit_reviews(db, actor, run_id, body, key)
    db.commit()
    return result


class SingleReview(ClaimDecision):
    report_version_id: str
    report_hash: str


@router.post("/{run_id}/claim-reviews")
def single(
    run_id: str,
    body: SingleReview,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    item = ClaimDecision.model_validate(
        body.model_dump(exclude={"report_version_id", "report_hash"})
    )
    result = submit_reviews(
        db,
        actor,
        run_id,
        ReviewBatch(
            report_version_id=body.report_version_id, report_hash=body.report_hash, decisions=[item]
        ),
        key,
    )
    db.commit()
    return {"review_id": result["review_ids"][0], "report_version_id": result["report_version_id"]}
