"""Atomic explicit review with append-only evidence and conservative conflict preservation."""

from typing import Any

from sqlalchemy import select

from app.access.service import require_resource
from app.diagnosis.normalization import UNITS
from app.diagnosis.questions import RISK_FIELDS
from app.incidents.assets import asset_summary
from app.incidents.models import Evidence, EvidenceSnapshot, Incident
from app.incidents.schemas import IncidentInput, Reading
from app.incidents.service import current_snapshot
from app.shared.audit import AuditRecord
from app.shared.errors import DomainError
from app.shared.versioning import content_hash


def validate_value(db, actor, key, value):
    from pydantic import ValidationError

    try:
        if key == "ocr_text":
            if type(value) is not str or not value.strip() or len(value) > 5000:
                raise DomainError("EVIDENCE_VALUE_INVALID")
        elif key in UNITS:
            if type(value) not in {int, float} or value < 0:
                raise DomainError("EVIDENCE_VALUE_INVALID")
            Reading(metric=key, value=value, unit=UNITS[key])
        elif key == "alarm_code":
            IncidentInput(raw_description="review", alarm_code=value)
        elif key == "preheating_confirmed":
            IncidentInput(raw_description="review", preheating_confirmed=value)
        elif key == "asset_association":
            if type(value) is not str or asset_summary(db, actor, value)["model"] != "APX-240":
                raise DomainError("EVIDENCE_ASSET_INVALID")
        else:
            IncidentInput(raw_description="review", observations={key: value})
    except ValidationError:
        raise DomainError("EVIDENCE_VALUE_INVALID") from None
    if value is None or value == "UNKNOWN":
        raise DomainError("EVIDENCE_VALUE_UNCONFIRMED")


def rebuild_snapshot(db, incident_id, resolved=()):
    prior = current_snapshot(db, incident_id)
    rows = db.scalars(
        select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.created_at)
    ).all()
    replaced = {r.supersedes_id for r in rows if r.supersedes_id}
    active = [r for r in rows if r.id not in replaced and r.state in {"CONFIRMED", "CORRECTED"}]
    facts: dict[str, Any] = {}
    conflicts, ids = set(prior.contradictions) - set(resolved), []
    incident = db.get(Incident, incident_id)
    asset_ids = {incident.asset_id} if incident.asset_id else set()
    for row in active:
        key, value = row.evidence_key, row.value["value"]
        ids.append(row.id)
        if key == "asset_association":
            asset_ids.add(value)
            continue
        if key in facts and facts[key] != value:
            conflicts.add(key)
        facts[key] = value
    if len(asset_ids) > 1:
        conflicts.add("asset_association")
    unknowns = [
        item for item in prior.unknowns if not any(item.startswith(key + " ") for key in facts)
    ]
    snapshot = EvidenceSnapshot(
        incident_id=incident_id,
        facts=facts,
        evidence_ids=ids,
        contradictions=sorted(conflicts),
        unknowns=unknowns,
        content_hash=content_hash([facts, ids, unknowns, sorted(conflicts)]),
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def review_batch(db, actor, incident_id, body, key):
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    require_resource(db, actor, "INCIDENT", incident_id, write=True)
    db.get(Incident, incident_id, with_for_update=True)
    if db.scalar(
        select(AuditRecord.id).where(
            AuditRecord.resource_id == incident_id,
            AuditRecord.action == "EVIDENCE_REVIEW_BATCH",
            AuditRecord.details["idempotency_key"].as_string() == key,
        )
    ):
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    prepared = []
    prior = current_snapshot(db, incident_id)
    for decision in body.decisions:
        original = db.get(Evidence, decision.evidence_id)
        if not original or original.incident_id != incident_id:
            raise DomainError("NOT_FOUND", 404)
        if original.media_id:
            from app.evidence.policy import require_evidence_read

            require_evidence_read(db, actor, original)
        if original.version != decision.expected_evidence_version or db.scalar(
            select(Evidence.id).where(Evidence.supersedes_id == original.id)
        ):
            raise DomainError("EVIDENCE_REVIEW_STALE", 409)
        if original.state != "CANDIDATE" and not (
            decision.decision == "CORRECTED" and original.state in {"CONFIRMED", "CORRECTED"}
        ):
            raise DomainError("EVIDENCE_STATE_NOT_REVIEWABLE", 409)
        value = dict(original.value)
        if decision.corrected_content is not None:
            if set(decision.corrected_content) != {"value"}:
                raise DomainError("EVIDENCE_CORRECTION_INVALID")
            value["value"] = decision.corrected_content["value"]
        if (
            original.evidence_key in prior.contradictions
            or original.evidence_key in RISK_FIELDS
            and original.value.get("value") is True
        ) and original.state != "CANDIDATE":
            actor.require_role("EXPERT")
        if decision.decision != "REJECTED":
            validate_value(db, actor, original.evidence_key, value["value"])
        elif original.evidence_key in RISK_FIELDS and original.value.get("value") is True:
            actor.require_role("EXPERT")
        prepared.append((original, decision, value))
    outputs, resolved = [], []
    for original, decision, value in prepared:
        version = (
            db.scalar(
                select(Evidence.version)
                .where(
                    Evidence.incident_id == incident_id,
                    Evidence.evidence_key == original.evidence_key,
                )
                .order_by(Evidence.version.desc())
                .limit(1)
            )
            or 0
        ) + 1
        row = Evidence(
            incident_id=incident_id,
            media_id=original.media_id,
            evidence_key=original.evidence_key,
            version=version,
            supersedes_id=original.id,
            state=decision.decision,
            source=original.source,
            value=value,
            reviewer_id=actor.id,
            locators=original.locators,
            provenance=original.provenance,
        )
        db.add(row)
        db.flush()
        if row.media_id:
            from app.evidence.policy import bind_evidence_policy

            bind_evidence_policy(db, row, row.media_id)
        outputs.append({"evidence_id": row.id, "version": row.version, "state": row.state})
        if decision.decision == "CORRECTED" and "EXPERT" in actor.roles:
            resolved.append(original.evidence_key)
        db.add(
            AuditRecord(
                actor_id=actor.id,
                actor_version=str(actor.auth_version),
                action="EVIDENCE_REVIEWED",
                resource_id=row.id,
                details={
                    "original_id": original.id,
                    "decision": decision.decision,
                    "review_note": decision.review_note,
                    "batch_key": key,
                },
            )
        )
    snapshot = rebuild_snapshot(db, incident_id, resolved)
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="EVIDENCE_REVIEW_BATCH",
            resource_id=incident_id,
            details={
                "idempotency_key": key,
                "new_versions": outputs,
                "snapshot_hash": snapshot.content_hash,
            },
        )
    )
    db.flush()
    return {
        "versions": outputs,
        "evidence_snapshot_id": snapshot.id,
        "conflicts": snapshot.contradictions,
    }
