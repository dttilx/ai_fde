from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant
from app.knowledge.models import SourceRecord
from app.shared.auth_context import ActorContext


def authorized_source_ids(db: Session, actor: ActorContext) -> list[str]:
    # SQL scope filter is applied before any ranking, keyword search or vector distance.
    records = db.execute(
        select(SourceRecord.id, PolicyBinding.readable_by)
        .join(ResourceGrant, ResourceGrant.resource_id == SourceRecord.id)
        .join(PolicyBinding, PolicyBinding.resource_id == SourceRecord.id)
        .where(
            ResourceGrant.user_id == actor.id,
            ResourceGrant.resource_type == "SOURCE",
            ResourceGrant.active.is_(True),
            ResourceGrant.permission.in_(("READ", "WRITE")),
            PolicyBinding.resource_type == "SOURCE",
        )
    )
    return sorted(
        {
            source_id
            for source_id, readers in records
            if isinstance(source_id, str) and isinstance(readers, list) and actor.id in readers
        }
    )
