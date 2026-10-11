from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.service import require_resource
from app.evidence.review import review_batch
from app.evidence.schemas import (
    VIDEO_BYTES,
    EvidenceExclude,
    EvidenceReview,
    ReviewBatch,
    ReviewDecision,
)
from app.evidence.service import accessible_media, upload_media
from app.incidents.models import Evidence
from app.shared.auth_context import ActorContext, current_actor
from app.shared.db import get_db
from app.shared.errors import DomainError
from app.shared.storage import storage

router = APIRouter(prefix="/api")


class RetentionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/media/{media_id}/tombstone")
def tombstone(
    media_id: str,
    body: RetentionInput,
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    from app.evidence.retention import tombstone_media

    record = tombstone_media(db, actor, media_id, body.expected_checksum, body.reason)
    db.commit()
    return {
        "media_id": media_id,
        "tombstone_id": record.id,
        "availability": "UNAVAILABLE",
        "physical_purge": "NOT_PERFORMED",
    }


@router.post("/incidents/{incident_id}/evidence/{evidence_id}/review")
def review_one(
    incident_id: str,
    evidence_id: str,
    body: ReviewDecision,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    batch = ReviewBatch(decisions=[EvidenceReview(evidence_id=evidence_id, **body.model_dump())])
    return reviews(incident_id, batch, key, actor, db)


@router.post("/incidents/{incident_id}/evidence/{evidence_id}/exclude")
def exclude_one(
    incident_id: str,
    evidence_id: str,
    body: EvidenceExclude,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    batch = ReviewBatch(
        decisions=[
            EvidenceReview(evidence_id=evidence_id, decision="REJECTED", **body.model_dump())
        ]
    )
    return reviews(incident_id, batch, key, actor, db)


@router.post("/incidents/{incident_id}/evidence/review-batch")
def reviews(
    incident_id: str,
    body: ReviewBatch,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    result = review_batch(db, actor, incident_id, body, key)
    db.commit()
    return result


@router.post("/incidents/{incident_id}/media")
async def upload(
    incident_id: str,
    file: Annotated[UploadFile, File()],
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    require_resource(db, actor, "INCIDENT", incident_id, write=True)
    try:
        data = await file.read(VIDEO_BYTES + 1)
    finally:
        await file.close()
    if len(data) > VIDEO_BYTES:
        raise DomainError("MEDIA_TOO_LARGE", 413)
    media, job = upload_media(db, actor, incident_id, data, file.content_type, key)
    db.commit()
    return {
        "media_id": media.id,
        "job_id": job.id,
        "scan_status": media.scan_status,
        "processing_status": media.processing_status,
    }


@router.get("/media/{media_id}/content")
def content(
    media_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)
):
    media = accessible_media(db, actor, media_id)
    return Response(
        storage().get(media.storage_ref),
        media_type=media.content_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/media/{media_id}/frames/{frame_index}/content")
def frame_content(
    media_id: str,
    frame_index: int,
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    from app.shared.jobs.models import Job

    media = accessible_media(db, actor, media_id)
    job = db.get(Job, media.job_id)
    frames = job.result.get("frames", []) if job and job.result else []
    frame = next((item for item in frames if item["index"] == frame_index), None)
    if frame is None:
        raise DomainError("NOT_FOUND", 404)
    return Response(
        storage().get(frame["storage_ref"]),
        media_type="image/png",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/incidents/{incident_id}/evidence")
def evidence(
    incident_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)
):
    require_resource(db, actor, "INCIDENT", incident_id)
    rows = db.scalars(
        select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.created_at)
    ).all()
    result = []
    superseded = {row.supersedes_id for row in rows if row.supersedes_id}
    for row in rows:
        if row.media_id:
            try:
                from app.evidence.policy import require_evidence_read

                require_evidence_read(db, actor, row)
            except DomainError as exc:
                if exc.status == 404:
                    continue
                raise
        result.append(
            {
                "evidence_id": row.id,
                "version": row.version,
                "state": row.state,
                "media_id": row.media_id,
                "source": row.source,
                "key": row.evidence_key,
                "value": row.value,
                "locators": row.locators,
                "provenance": row.provenance,
                "reviewable": row.state == "CANDIDATE" and row.id not in superseded,
            }
        )
    from app.evidence.models import MediaAsset

    pending = False
    for media in db.scalars(select(MediaAsset).where(MediaAsset.incident_id == incident_id)):
        if media.processing_status in {"NOT_STARTED", "PROCESSING"}:
            try:
                accessible_media(db, actor, media.id)
                pending = True
            except DomainError as exc:
                if exc.status != 404:
                    raise
    return {"evidence": result, "processing_pending": pending}
