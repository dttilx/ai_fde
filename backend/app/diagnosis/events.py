"""Append-only scoped progress events; never emit raw model input or hidden reasoning."""

import json
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, func, select, text
from sqlalchemy.orm import Mapped, mapped_column

from app.access.models import new_id, now
from app.diagnosis.service import accessible_run
from app.incidents.service import get_incident
from app.shared.db import Base
from app.shared.errors import DomainError


class DiagnosisEvent(Base):
    __tablename__ = "diagnosis_events"
    __table_args__ = (UniqueConstraint("incident_id", "sequence"), UniqueConstraint("effect_key"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(50))
    effect_key: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def emit(db, run, event_type, effect_key, payload):
    # Serialize sequence allocation without retaining locks while the client is connected.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "events:" + run.incident_id}
    )
    existing = db.scalar(select(DiagnosisEvent).where(DiagnosisEvent.effect_key == effect_key))
    if existing:
        return existing
    sequence = (
        db.scalar(
            select(func.max(DiagnosisEvent.sequence)).where(
                DiagnosisEvent.incident_id == run.incident_id
            )
        )
        or 0
    ) + 1
    row = DiagnosisEvent(
        incident_id=run.incident_id,
        run_id=run.id,
        sequence=sequence,
        event_type=event_type,
        effect_key=effect_key,
        payload=payload,
    )
    db.add(row)
    db.flush()
    return row


def authorized_events(db, actor, incident_id, last_event_id=None):
    get_incident(db, actor, incident_id)
    sequence = 0
    if last_event_id:
        previous = db.get(DiagnosisEvent, last_event_id)
        if not previous or previous.incident_id != incident_id:
            raise DomainError("EVENT_CURSOR_INVALID", 409)
        accessible_run(db, actor, previous.run_id)
        sequence = previous.sequence
    rows = db.scalars(
        select(DiagnosisEvent)
        .where(
            DiagnosisEvent.incident_id == incident_id,
            DiagnosisEvent.sequence > sequence,
        )
        .order_by(DiagnosisEvent.sequence)
        .limit(100)
    ).all()
    result = []
    for row in rows:
        try:
            accessible_run(db, actor, row.run_id)
        except DomainError as exc:
            if exc.status == 404:
                continue
            raise
        result.append(
            {
                "event_id": row.id,
                "incident_id": incident_id,
                "sequence": row.sequence,
                "type": row.event_type,
                "occurred_at": row.occurred_at.isoformat(),
                "payload": row.payload,
                "trace_id": row.run_id,
            }
        )
    return result


def encode_sse(event):
    return (
        f"id: {event['event_id']}\nevent: {event['type']}\n"
        f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    )
