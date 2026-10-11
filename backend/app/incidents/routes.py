from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.incidents.schemas import IncidentInput
from app.incidents.service import create_incident, current_snapshot, get_incident
from app.shared.auth_context import ActorContext, current_actor
from app.shared.db import get_db

router = APIRouter(prefix="/api/incidents")
asset_router = APIRouter(prefix="/api/assets")


@asset_router.get("/{asset_id}")
def get_asset(
    asset_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)
):
    from app.incidents.assets import asset_summary

    return asset_summary(db, actor, asset_id)


@router.post("")
def create(
    body: IncidentInput,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    incident, snapshot = create_incident(db, actor, body, key)
    db.commit()
    return {
        "incident_id": incident.id,
        "snapshot_id": snapshot.id,
        "status": "OPEN",
        "facts": snapshot.facts,
        "unconfirmed_information": snapshot.unknowns,
        "contradictions": snapshot.contradictions,
        "immediate_safety_notice": incident.immediate_safety_notice,
    }


@router.get("/{incident_id}")
def get(
    incident_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)
):
    incident = get_incident(db, actor, incident_id)
    snapshot = current_snapshot(db, incident.id)
    return {
        "incident_id": incident.id,
        "raw_description": incident.raw_description,
        "facts": snapshot.facts,
        "snapshot_id": snapshot.id,
        "immediate_safety_notice": incident.immediate_safety_notice,
    }
