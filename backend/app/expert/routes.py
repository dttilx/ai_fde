from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.expert.schemas import ExpertOpen, ExpertRevision
from app.expert.service import open_review, revise
from app.shared.auth_context import ActorContext, current_actor
from app.shared.db import get_db

router = APIRouter(prefix="/api")


@router.post("/diagnoses/{run_id}/expert-reviews")
def create_review(
    run_id: str,
    body: ExpertOpen,
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    review = open_review(db, actor, run_id, body)
    db.commit()
    return {"expert_review_id": review.id, "status": review.status, "run_id": review.run_id}


@router.post("/expert-reviews/{review_id}/revision")
def revision(
    review_id: str,
    body: ExpertRevision,
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    review = revise(db, actor, review_id, body)
    db.commit()
    return {
        "expert_review_id": review.id,
        "status": review.status,
        "report_version_ids": review.report_version_ids,
    }
