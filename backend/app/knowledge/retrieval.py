from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.access.resource_policy import authorized_source_ids
from app.knowledge.indexing import fixture_embedding, fuse_rankings, query_tokens
from app.knowledge.models import SourceRecord
from app.shared.auth_context import ActorContext
from app.shared.errors import DomainError

RELATED = {
    "A101": ("H01", "WO-240-031"),
    "A203": ("H02", "WO-240-042"),
    "A310": ("H03", "WO-240-051"),
    "A401": ("H04", "WO-240-063"),
    "A520": ("H05", "WO-240-077"),
}


def retrieve(
    db: Session,
    actor: ActorContext,
    alarm: str,
    query: str,
    scope: list[str],
    *,
    query_vector=None,
    vector_model=None,
    index_version=None,
) -> list[dict]:
    permitted = set(authorized_source_ids(db, actor)).intersection(scope)
    if not permitted:
        return []
    # Reviewed cases are independent releases. Never let a draft or an unrelated
    # newer case release replace the pinned manual release.
    from app.feedback.models import VerifiedCase

    approved = db.scalars(
        select(SourceRecord)
        .join(VerifiedCase, VerifiedCase.knowledge_release_id == SourceRecord.release_id)
        .where(
            SourceRecord.id.in_(permitted),
            SourceRecord.collection == "APPROVED_CASE",
            SourceRecord.metadata_fields["status"].as_string().in_(["VERIFIED", "ACTIVE"]),
            SourceRecord.metadata_fields["model"].as_string() == "APX-240",
            SourceRecord.metadata_fields["alarm_code"].as_string() == alarm,
            SourceRecord.metadata_fields["reviewer_id"].as_string().is_not(None),
            SourceRecord.metadata_fields["publication_id"].as_string().is_not(None),
            VerifiedCase.status == "PUBLISHED",
        )
    ).all()
    approved_ids = {
        record.id
        for record in approved
        if record.metadata_fields.get("reviewer_id")
        and record.metadata_fields.get("publication_id")
    }
    # Always pin exact rules/alarms and their source-grounded reference routes.
    keys = [f"SAFE-0{i}" for i in range(1, 6)] + [alarm, "MANUAL-P2", *RELATED.get(alarm, ())]
    exact = db.scalars(
        select(SourceRecord).where(
            SourceRecord.id.in_(permitted),
            SourceRecord.source_key.in_(keys),
            SourceRecord.collection != "APPROVED_CASE",
        )
    ).all()
    # Release selection avoids mixed parser/index versions when the scope includes older imports.
    if exact:
        from app.knowledge.models import KnowledgeRelease

        release = db.scalar(
            select(KnowledgeRelease)
            .where(KnowledgeRelease.id.in_([r.release_id for r in exact]))
            .order_by(KnowledgeRelease.created_at.desc())
        )
        if release is None:
            raise DomainError("KNOWLEDGE_RELEASE_MISSING", 409)
        permitted = {
            record.id
            for record in db.scalars(
                select(SourceRecord).where(
                    SourceRecord.id.in_(permitted),
                    SourceRecord.release_id == release.id,
                    SourceRecord.collection != "APPROVED_CASE",
                )
            )
        }
        exact = [record for record in exact if record.release_id == release.id]
    else:
        permitted = {
            record.id
            for record in db.scalars(
                select(SourceRecord).where(
                    SourceRecord.id.in_(permitted), SourceRecord.collection != "APPROVED_CASE"
                )
            )
        }
    permitted.update(approved_ids)
    tokens = query_tokens(alarm, query)
    clauses = [SourceRecord.content.contains(token, autoescape=True) for token in tokens if token]
    keyword = (
        db.scalars(
            select(SourceRecord)
            .where(SourceRecord.id.in_(permitted), or_(*clauses))
            .order_by(SourceRecord.source_key)
            .limit(20)
        ).all()
        if clauses
        else []
    )
    from app.shared.config import settings

    embedding_mode = "KEYWORD_ONLY"
    vector_ranking = []
    if query_vector is not None:
        if not vector_model or not index_version:
            raise DomainError("QUERY_VECTOR_VERSION_REQUIRED", 409)
        from app.knowledge.vectors import ranked_vectors

        vector_ranking = ranked_vectors(db, permitted, query_vector, vector_model, index_version)
        embedding_mode = "VERSIONED_VECTOR" if vector_ranking else "KEYWORD_ONLY"
    elif settings().provider_mode == "FIXTURE":
        vector = fixture_embedding(query)
        vector_ranking = list(
            db.scalars(
                select(SourceRecord)
                .where(SourceRecord.id.in_(permitted))
                .order_by(SourceRecord.embedding.cosine_distance(vector))
                .limit(20)
            ).all()
        )
        embedding_mode = "FIXTURE"
    fused = fuse_rankings([keyword, vector_ranking])
    scores = {record.id: score for record, score in fused}
    pinned = {record.id for record in exact}
    optional = [record for record, _ in fused if record.id not in pinned][:8]
    return [
        {
            "source_id": row.id,
            "source_key": row.source_key,
            "collection": row.collection,
            "release_id": row.release_id,
            "content": row.content,
            "locator": row.locator,
            "checksum": row.checksum,
            "pinned": row.id in pinned,
            "rrf_score": scores.get(row.id, 0),
            "embedding_mode": embedding_mode,
            "egress": "DENY",
        }
        for row in list(exact) + optional
    ]
