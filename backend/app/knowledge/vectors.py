"""Scope first; actual vectors only compare to the same model/index/dimension."""

import math

from sqlalchemy import select

from app.access.resource_policy import authorized_source_ids
from app.knowledge.models import SourceRecord
from app.knowledge.vector_models import SourceEmbedding
from app.shared.errors import DomainError


def valid_vector(vector):
    return (
        isinstance(vector, list)
        and 1 <= len(vector) <= 4096
        and all(type(v) in (int, float) and math.isfinite(v) for v in vector)
        and any(v != 0 for v in vector)
    )


def add_vectors(db, actor, source_ids, result, index_version):
    if result.mode not in {"REAL_LOCAL", "REAL_APPROVED_EXTERNAL"} or result.status != "SUCCEEDED":
        raise DomainError("REAL_VECTOR_RESULT_REQUIRED", 409)
    allowed = set(authorized_source_ids(db, actor))
    vectors = result.data.get("vectors", [])
    dimensions = result.data.get("dimensions")
    if not source_ids or len(set(source_ids)) != len(source_ids) or len(vectors) != len(source_ids):
        raise DomainError("VECTOR_SOURCE_ALIGNMENT_INVALID", 409)
    rows = []
    for source_id, vector in zip(source_ids, vectors, strict=True):
        if source_id not in allowed:
            raise DomainError("NOT_FOUND", 404)
        source = db.get(SourceRecord, source_id)
        if source is None or not valid_vector(vector) or len(vector) != dimensions:
            raise DomainError("VECTOR_SOURCE_ALIGNMENT_INVALID", 409)
        if db.scalar(
            select(SourceEmbedding.id).where(
                SourceEmbedding.source_id == source_id,
                SourceEmbedding.model == result.model,
                SourceEmbedding.index_version == index_version,
            )
        ):
            raise DomainError("VECTOR_VERSION_EXISTS", 409)
        rows.append(
            SourceEmbedding(
                source_id=source_id,
                source_checksum=source.checksum,
                model=result.model,
                index_version=index_version,
                mode=result.mode,
                dimensions=dimensions,
                vector=vector,
            )
        )
    db.add_all(rows)
    db.flush()


def ranked_vectors(db, permitted, vector, model, index_version):
    if not valid_vector(vector):
        raise DomainError("QUERY_VECTOR_INVALID", 409)
    return db.scalars(
        select(SourceRecord)
        .join(SourceEmbedding)
        .where(
            SourceRecord.id.in_(permitted),
            SourceEmbedding.source_checksum == SourceRecord.checksum,
            SourceEmbedding.model == model,
            SourceEmbedding.index_version == index_version,
            SourceEmbedding.dimensions == len(vector),
        )
        .order_by(SourceEmbedding.vector.cosine_distance(vector))
        .limit(20)
    ).all()
