from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.service import require_resource
from app.knowledge.assessment_models import AssessmentCache
from app.shared.auth_context import ActorContext
from app.shared.versioning import content_hash


def assessment_cache_key(
    projection: dict,
    source_version: str,
    rubric: str,
    model: str,
    policy_version: str,
    scope_hash: str,
) -> str:
    # Cache lookup never grants access: caller must reauthorize all contributors before reuse.
    return content_hash([projection, source_version, rubric, model, policy_version, scope_hash])


def lookup(
    db: Session, actor: ActorContext, key: str, source_id: str, scope_hash: str
) -> dict | None:
    require_resource(db, actor, "SOURCE", source_id)
    row = db.scalar(
        select(AssessmentCache)
        .where(
            AssessmentCache.cache_key == key,
            AssessmentCache.source_id == source_id,
            AssessmentCache.scope_hash == scope_hash,
            AssessmentCache.expires_at > datetime.now(UTC),
        )
        .order_by(AssessmentCache.created_at.desc())
    )
    return {**row.payload, "_cache_record_id": row.id} if row else None


def store(db: Session, key: str, source_id: str, scope_hash: str, payload: dict) -> None:
    # Expired records are retained; fresh entries append rather than overwrite provenance.
    db.add(
        AssessmentCache(
            cache_key=key,
            source_id=source_id,
            scope_hash=scope_hash,
            payload=payload,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
