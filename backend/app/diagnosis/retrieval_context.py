import hashlib

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.diagnosis.models import Citation
from app.knowledge.models import SourceRecord
from app.shared.errors import DomainError


def validate_media_snapshot(db, actor, snapshot):
    from sqlalchemy import select

    from app.evidence.policy import require_evidence_read
    from app.incidents.models import Evidence

    for row in db.scalars(select(Evidence).where(Evidence.id.in_(snapshot.evidence_ids))):
        if row.state not in {"CONFIRMED", "CORRECTED"}:
            raise DomainError("SNAPSHOT_CONTAINS_UNCONFIRMED_EVIDENCE", 409)
        if row.media_id:
            require_evidence_read(db, actor, row)


def require_reviewed_media(db, actor, incident_id, snapshot):
    from sqlalchemy import select

    from app.evidence.models import MediaAsset
    from app.evidence.service import accessible_media
    from app.incidents.models import Evidence

    validate_media_snapshot(db, actor, snapshot)
    rows = db.scalars(select(Evidence).where(Evidence.incident_id == incident_id)).all()
    replaced = {row.supersedes_id for row in rows if row.supersedes_id}
    for row in rows:
        if row.media_id and row.state == "CANDIDATE" and row.id not in replaced:
            accessible_media(db, actor, row.media_id)
            raise DomainError("MEDIA_REVIEW_REQUIRED", 409)
    for media in db.scalars(select(MediaAsset).where(MediaAsset.incident_id == incident_id)):
        if media.processing_status in {"NOT_STARTED", "PROCESSING"}:
            accessible_media(db, actor, media.id)
            raise DomainError("MEDIA_PROCESSING_PENDING", 409)


def snapshot_asset_id(db, incident, snapshot):
    from sqlalchemy import select

    from app.incidents.models import Evidence

    assets = {incident.asset_id} if incident.asset_id else set()
    assets.update(
        row.value["value"]
        for row in db.scalars(
            select(Evidence).where(
                Evidence.id.in_(snapshot.evidence_ids),
                Evidence.evidence_key == "asset_association",
                Evidence.state.in_(("CONFIRMED", "CORRECTED")),
            )
        )
    )
    if len(assets) > 1:
        raise DomainError("ASSET_EVIDENCE_CONFLICT", 409)
    return next(iter(assets), None)


def citations(db: Session, sources: list[dict]) -> list[dict]:
    result = []
    for source in sources:
        source_id = source["source_id"]
        record = db.get(SourceRecord, source_id)
        if (
            record is None
            or record.checksum != source["checksum"]
            or record.release_id != source["release_id"]
            or record.content != source["content"]
            or record.locator != source["locator"]
            or record.collection != source["collection"]
            or hashlib.sha256(record.content.encode()).hexdigest() != record.checksum
        ):
            raise DomainError("CITATION_SOURCE_CHANGED", 409)
        citation_id = f"{record.release_id}:{record.source_key}"
        existing = db.get(Citation, citation_id)
        if existing is None:
            payload = {
                "citation_id": citation_id,
                "source_type": record.collection,
                "source_ref": record.source_key,
                "knowledge_release_id": record.release_id,
                "locator": f"第{record.locator['page']}页 / {record.locator['section']}",
                "excerpt": record.content,
                "checksum": record.checksum,
            }
            db.execute(
                insert(Citation)
                .values(
                    id=citation_id,
                    source_id=source_id,
                    release_id=record.release_id,
                    payload=payload,
                )
                .on_conflict_do_nothing(index_elements=[Citation.id])
            )
        else:
            payload = existing.payload
        result.append(payload)
    db.flush()
    return result


def asset_context(db: Session, actor, asset_id: str | None) -> dict | None:
    """Asset lookup is scoped context, never a fault citation or a QR authorization grant."""
    if asset_id is None:
        return None
    from app.incidents.assets import asset_summary

    return asset_summary(db, actor, asset_id)
