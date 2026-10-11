from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.resource_policy import authorized_source_ids
from app.diagnosis.citation_assessment import validate_citations
from app.diagnosis.models import ReportVersion
from app.diagnosis.service import accessible_run
from app.knowledge.assessment_models import RetrievalAssessment
from app.knowledge.passage_assessment import summary_status
from app.shared.auth_context import ActorContext, current_actor
from app.shared.db import get_db, require_record

router = APIRouter(prefix="/api")


@router.get("/diagnoses/{run_id}/retrieval-assessments")
def assessments(
    run_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)
):
    run = accessible_run(db, actor, run_id)
    if run.report_version_id:
        report = require_record(db, ReportVersion, run.report_version_id)
        validate_citations(db, actor, report.payload["evidence_sources"])
    permitted = set(authorized_source_ids(db, actor))
    rows = db.scalars(
        select(RetrievalAssessment)
        .where(RetrievalAssessment.run_id == run.id, RetrievalAssessment.source_id.in_(permitted))
        .order_by(RetrievalAssessment.created_at.asc().nulls_first(), RetrievalAssessment.id)
    ).all()
    latest_round = max((row.provenance.get("retrieval_round", 1) for row in rows), default=1)
    latest = {}
    for row in rows:
        if row.provenance.get("retrieval_round", 1) == latest_round:
            latest[row.source_id] = row.payload
    payloads = sorted(latest.values(), key=lambda item: item["hybrid_rank"])
    return {
        "diagnosis_run_id": run.id,
        "retrieval_round": latest_round,
        "assessments": payloads,
        "status": summary_status(payloads),
    }
