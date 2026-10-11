"""Private upload transaction; perception completion never confirms a candidate."""

from sqlalchemy import func, select

from app.access.models import PolicyBinding, ResourceGrant, new_id
from app.access.service import require_resource
from app.evidence.models import MediaAsset
from app.evidence.schemas import IMAGE_COUNT, VIDEO_COUNT
from app.evidence.validation import inspect_media
from app.incidents.models import Incident
from app.shared.audit import AuditRecord
from app.shared.errors import DomainError
from app.shared.jobs.service import create_job
from app.shared.storage import digest, storage


def upload_media(db, actor, incident_id, data, content_type, key):
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    require_resource(db, actor, "INCIDENT", incident_id, write=True)
    incident = db.get(Incident, incident_id, with_for_update=True)
    if not incident or incident.organization_id != actor.organization_id:
        raise DomainError("NOT_FOUND", 404)
    checksum = digest(data)
    if db.scalar(
        select(MediaAsset.id).where(
            MediaAsset.incident_id == incident_id,
            (MediaAsset.checksum == checksum) | (MediaAsset.idempotency_key == key),
        )
    ):
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    metadata = inspect_media(data, content_type)
    count = db.scalar(
        select(func.count())
        .select_from(MediaAsset)
        .where(
            MediaAsset.incident_id == incident_id, MediaAsset.media_type == metadata["media_type"]
        )
    )
    if count >= (IMAGE_COUNT if metadata["media_type"] == "IMAGE" else VIDEO_COUNT):
        raise DomainError("MEDIA_COUNT_LIMIT", 413)
    from app.shared.config import settings

    if settings().externally_accessible:
        # This stage has no antivirus adapter. Never silently mark unscanned data CLEAN.
        raise DomainError("MEDIA_SCANNER_REQUIRED", 503)
    policy = db.scalar(
        select(PolicyBinding).where(
            PolicyBinding.resource_type == "INCIDENT", PolicyBinding.resource_id == incident_id
        )
    )
    obj = storage().put(data, content_type)
    media = MediaAsset(
        id=new_id(),
        incident_id=incident_id,
        checksum=checksum,
        storage_ref=obj.key,
        idempotency_key=key,
        byte_size=len(data),
        created_by=actor.id,
        lineage={
            "incident_id": incident_id,
            "policy_id": policy.id,
            "policy_version": policy.version,
        },
        scan_status="NOT_PERFORMED",
        **metadata,
    )
    job = create_job(
        db,
        incident_id,
        actor.id,
        "VIDEO" if metadata["media_type"] == "VIDEO" else "OCR",
        key,
        {"media_id": media.id, "actor_version": actor.auth_version},
    )
    media.job_id = job.id
    db.add(media)
    db.add(
        PolicyBinding(
            resource_type="MEDIA",
            resource_id=media.id,
            classification=policy.classification,
            origin=policy.origin,
            readable_by=list(policy.readable_by),
            egress=policy.egress,
            approved_providers=list(policy.approved_providers),
            approved_purposes=list(policy.approved_purposes),
            basis=policy.basis,
            expires_at=policy.expires_at,
        )
    )
    for grant in db.scalars(
        select(ResourceGrant).where(
            ResourceGrant.resource_type == "INCIDENT",
            ResourceGrant.resource_id == incident_id,
            ResourceGrant.active.is_(True),
        )
    ):
        db.add(
            ResourceGrant(
                user_id=grant.user_id,
                resource_type="MEDIA",
                resource_id=media.id,
                permission=grant.permission,
            )
        )
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="MEDIA_UPLOADED",
            resource_id=media.id,
            details={"checksum": checksum, "scan_status": "NOT_PERFORMED", "job_id": job.id},
        )
    )
    db.flush()
    return media, job


def accessible_media(db, actor, media_id):
    media = db.get(MediaAsset, media_id)
    if not media:
        raise DomainError("NOT_FOUND", 404)
    require_resource(db, actor, "INCIDENT", media.incident_id)
    require_resource(db, actor, "MEDIA", media.id)
    from app.evidence.retention import tombstone_record

    if tombstone_record(db, media.id):
        raise DomainError("MEDIA_UNAVAILABLE_RETAINED_REFERENCE", 410)
    return media
