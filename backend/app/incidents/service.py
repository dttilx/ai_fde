from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant
from app.access.service import require_resource
from app.diagnosis.normalization import UNITS, normalize
from app.incidents.models import Asset, Evidence, EvidenceSnapshot, Incident
from app.safety.service import evaluate
from app.shared.audit import AuditRecord
from app.shared.auth_context import ActorContext
from app.shared.errors import DomainError
from app.shared.versioning import content_hash


def create_incident(
    db: Session, actor: ActorContext, body, key: str
) -> tuple[Incident, EvidenceSnapshot]:
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    if db.scalar(
        select(Incident).where(Incident.owner_id == actor.id, Incident.idempotency_key == key)
    ):
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    if body.asset_id:
        require_resource(db, actor, "ASSET", body.asset_id)
        asset = db.get(Asset, body.asset_id)
        if not asset or asset.model != "APX-240":
            raise DomainError("ASSET_NOT_APX240")
    facts, unknowns, contradictions, origins = normalize(body)
    safety = evaluate(body.raw_description, facts, contradictions=tuple(contradictions))
    incident = Incident(
        owner_id=actor.id,
        organization_id=actor.organization_id,
        idempotency_key=key,
        raw_description=body.raw_description,
        raw_form=body.model_dump(),
        asset_id=body.asset_id,
        immediate_safety_notice=safety.model_dump() if safety.safety_blocked else None,
    )
    db.add(incident)
    db.flush()
    ids = []
    for field, value in facts.items():
        evidence = Evidence(
            incident_id=incident.id,
            evidence_key=field,
            state="CONFIRMED",
            source=origins[field],
            value={"value": value, "unit": UNITS.get(field)},
            reviewer_id=actor.id,
        )
        db.add(evidence)
        db.flush()
        ids.append(evidence.id)
    snapshot = EvidenceSnapshot(
        incident_id=incident.id,
        evidence_ids=ids,
        facts=facts,
        unknowns=unknowns,
        contradictions=contradictions,
        content_hash=content_hash([facts, ids, unknowns, contradictions]),
    )
    db.add(snapshot)
    db.add(
        ResourceGrant(
            user_id=actor.id, resource_type="INCIDENT", resource_id=incident.id, permission="WRITE"
        )
    )
    db.add(
        PolicyBinding(
            resource_type="INCIDENT",
            resource_id=incident.id,
            classification="FIELD_RECORD",
            origin="LIVE_FIELD",
            readable_by=[actor.id],
            egress="DENY",
        )
    )
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="INCIDENT_CREATED",
            resource_id=incident.id,
            details={"snapshot_hash": snapshot.content_hash, "safety_status": safety.status},
        )
    )
    db.flush()
    return incident, snapshot


def get_incident(db: Session, actor: ActorContext, incident_id: str) -> Incident:
    require_resource(db, actor, "INCIDENT", incident_id)
    incident = db.get(Incident, incident_id)
    if not incident or incident.organization_id != actor.organization_id:
        raise DomainError("NOT_FOUND", 404)
    return incident


def current_snapshot(db: Session, incident_id: str) -> EvidenceSnapshot:
    snapshot = db.scalar(
        select(EvidenceSnapshot)
        .where(EvidenceSnapshot.incident_id == incident_id)
        .order_by(EvidenceSnapshot.created_at.desc())
    )
    if not snapshot:
        raise DomainError("EVIDENCE_SNAPSHOT_MISSING", 409)
    return snapshot
