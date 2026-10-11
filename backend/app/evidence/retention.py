"""Append-only access withdrawal; physical purging is a separate operator action."""

from sqlalchemy import select, text

from app.access.service import require_resource
from app.evidence.models import MediaAsset
from app.shared.audit import AuditRecord
from app.shared.errors import DomainError


def tombstone_record(db, media_id):
    return db.scalar(
        select(AuditRecord).where(
            AuditRecord.resource_id == media_id, AuditRecord.action == "MEDIA_TOMBSTONED"
        )
    )


def tombstone_media(db, actor, media_id, expected_checksum, reason):
    actor.require_role("EXPERT")
    media = db.get(MediaAsset, media_id)
    if media is None:
        raise DomainError("NOT_FOUND", 404)
    require_resource(db, actor, "INCIDENT", media.incident_id, write=True)
    require_resource(db, actor, "MEDIA", media_id)
    if not reason.strip() or len(reason) > 1000:
        raise DomainError("RETENTION_REASON_REQUIRED", 422)
    if expected_checksum != media.checksum:
        raise DomainError("MEDIA_VERSION_CONFLICT", 409)
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "tombstone:" + media_id}
    )
    prior = tombstone_record(db, media_id)
    if prior:
        return prior
    record = AuditRecord(
        actor_id=actor.id,
        actor_version=str(actor.auth_version),
        action="MEDIA_TOMBSTONED",
        resource_id=media_id,
        details={"checksum": media.checksum, "reason": reason, "physical_purge": "NOT_PERFORMED"},
    )
    db.add(record)
    db.flush()
    return record
