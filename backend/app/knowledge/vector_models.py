"""Real embeddings are versioned separately from the 16-dimensional workflow fixture."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.access.models import new_id
from app.shared.db import Base


class SourceEmbedding(Base):
    __tablename__ = "source_embeddings"
    __table_args__ = (
        UniqueConstraint("source_id", "model", "index_version"),
        CheckConstraint("dimensions BETWEEN 1 AND 4096"),
        CheckConstraint("mode IN ('REAL_LOCAL','REAL_APPROVED_EXTERNAL')"),
        CheckConstraint("vector_dims(vector) = dimensions"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"))
    source_checksum: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(160))
    index_version: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(40))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(Vector())
