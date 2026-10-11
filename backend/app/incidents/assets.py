import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant, User
from app.access.service import require_resource
from app.incidents.models import Asset, ServiceRestriction, WarrantyRecord
from app.incidents.service_policy import service_boundary, warranty_status
from app.shared.auth_context import ActorContext
from app.shared.config import PROJECT_ROOT
from app.shared.errors import DomainError


def asset_summary(db: Session, actor: ActorContext, asset_id: str) -> dict:
    require_resource(db, actor, "ASSET", asset_id)
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise DomainError("NOT_FOUND", 404)
    clock = datetime.now(UTC)
    warranty = db.scalar(
        select(WarrantyRecord)
        .where(WarrantyRecord.asset_id == asset_id)
        .order_by(WarrantyRecord.version.desc())
        .limit(1)
    )
    confirmed = bool(
        warranty
        and warranty.confirmed_by
        and warranty.confirmed_at
        and warranty.confirmed_at <= clock
    )
    status = (
        warranty_status(warranty.start_at, warranty.end_at, warranty.basis_ref, clock)
        if warranty and confirmed
        else "UNKNOWN"
    )
    versions = db.scalars(
        select(ServiceRestriction)
        .where(ServiceRestriction.asset_id == asset_id)
        .order_by(ServiceRestriction.version.desc())
    ).all()
    latest: dict[str, ServiceRestriction] = {}
    for row in versions:
        latest.setdefault(row.term_key, row)
    terms: list[dict] = [
        {
            "restriction_id": row.id,
            "version": row.version,
            "action_kind": row.action_kind,
            "required_service_party": row.required_service_party,
            "basis_ref": row.basis_ref,
            "effective_from": row.effective_from,
            "effective_until": row.effective_until,
            "confirmed": bool(row.confirmed_by and row.confirmed_at and row.confirmed_at <= clock),
        }
        for row in latest.values()
    ]
    # Only associated history sources the current actor can read are exposed.
    from app.access.resource_policy import authorized_source_ids
    from app.knowledge.models import SourceRecord

    readable = authorized_source_ids(db, actor)
    history = db.scalars(
        select(SourceRecord.source_key).where(
            SourceRecord.id.in_(readable), SourceRecord.source_key.in_(asset.history_refs)
        )
    ).all()
    return {
        "asset_id": asset.id,
        "model": asset.model,
        "origin": asset.origin,
        "history_refs": sorted(set(history)),
        "warranty": {
            "status": status,
            "as_of": clock.isoformat(),
            "version": warranty.version if warranty else None,
            "basis_ref": warranty.basis_ref if warranty and confirmed else None,
            "start_at": warranty.start_at.isoformat()
            if warranty and confirmed and warranty.start_at
            else None,
            "end_at": warranty.end_at.isoformat()
            if warranty and confirmed and warranty.end_at
            else None,
        },
        "service_boundaries": [
            {"action_kind": action, **service_boundary(status, action, terms, clock)}
            for action in sorted({term["action_kind"] for term in terms})
            if service_boundary(status, action, terms, clock)["restrictions"]
        ],
        "notice": "保修和服务条款不证明故障原因，也不授予维修权限；未知保修不阻断报障或紧急停机。",
    }


def initialize_demo_assets(db: Session) -> None:
    rows = json.loads((PROJECT_ROOT / "knowledge/seed/assets.json").read_text(encoding="utf-8"))
    users = db.scalars(select(User).where(User.enabled.is_(True))).all()
    for row in rows:
        if db.get(Asset, row["asset_id"]) is None:
            db.add(
                Asset(
                    id=row["asset_id"],
                    model=row["model"],
                    origin=row["origin"],
                    history_refs=row["history_refs"],
                )
            )
            db.flush()
            db.add(WarrantyRecord(asset_id=row["asset_id"], status="UNKNOWN"))
        readers = [user for user in users if {"FIELD_ENGINEER", "EXPERT"}.intersection(user.roles)]
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "ASSET", PolicyBinding.resource_id == row["asset_id"]
            )
        )
        if policy is None:
            db.add(
                PolicyBinding(
                    resource_type="ASSET",
                    resource_id=row["asset_id"],
                    classification="FIELD_RECORD",
                    origin="SELF_AUTHORED_SIMULATION",
                    readable_by=[user.id for user in readers],
                    egress="DENY",
                )
            )
        for user in users:
            if {"FIELD_ENGINEER", "EXPERT"}.intersection(user.roles):
                existing = db.scalar(
                    select(ResourceGrant).where(
                        ResourceGrant.user_id == user.id,
                        ResourceGrant.resource_type == "ASSET",
                        ResourceGrant.resource_id == row["asset_id"],
                    )
                )
                if existing:
                    continue
                db.add(
                    ResourceGrant(
                        user_id=user.id, resource_type="ASSET", resource_id=row["asset_id"]
                    )
                )
