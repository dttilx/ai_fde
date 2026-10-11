"""Media metadata plus the existing versioned Evidence, never a parallel evidence table."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.access.models import new_id, now
from app.incidents.models import Evidence as Evidence
from app.shared.db import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("incident_id", "checksum"),
        UniqueConstraint("incident_id", "idempotency_key"),
        CheckConstraint("media_type IN ('IMAGE','VIDEO')"),
        CheckConstraint("scan_status IN ('PENDING','CLEAN','REJECTED','FAILED','NOT_PERFORMED')"),
        CheckConstraint(
            "processing_status IN "
            "('NOT_STARTED','PROCESSING','CANDIDATES_READY','UNUSABLE','FAILED')"
        ),
        CheckConstraint("byte_size > 0 AND width > 0 AND height > 0"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    media_type: Mapped[str] = mapped_column(String(10))
    storage_ref: Mapped[str] = mapped_column(String(64))
    checksum: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scan_status: Mapped[str] = mapped_column(String(20), default="NOT_PERFORMED")
    scan_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(30), default="NOT_STARTED")
    processing_mode: Mapped[str] = mapped_column(String(30), default="FIXTURE")
    job_id: Mapped[str] = mapped_column(String(36))
    lineage: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
