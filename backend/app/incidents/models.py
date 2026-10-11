from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.access.models import new_id, now
from app.shared.db import Base


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    model: Mapped[str] = mapped_column(String(30))
    origin: Mapped[str] = mapped_column(String(50))
    history_refs: Mapped[list] = mapped_column(JSON, default=list)


class WarrantyRecord(Base):
    __tablename__ = "warranty_records"
    __table_args__ = (UniqueConstraint("asset_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    basis_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    confirmed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServiceRestriction(Base):
    __tablename__ = "service_restrictions"
    __table_args__ = (UniqueConstraint("asset_id", "term_key", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    term_key: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    action_kind: Mapped[str] = mapped_column(String(50))
    required_service_party: Mapped[str] = mapped_column(String(100))
    basis_ref: Mapped[str] = mapped_column(String(100))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[str] = mapped_column(String(36))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    raw_description: Mapped[str] = mapped_column(Text)
    raw_form: Mapped[dict] = mapped_column(JSON)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    immediate_safety_notice: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Evidence(Base):
    __tablename__ = "evidence_versions"
    __table_args__ = (
        UniqueConstraint("incident_id", "evidence_key", "version"),
        CheckConstraint(
            "state IN ('CANDIDATE','CONFIRMED','CORRECTED','REJECTED','UNAVAILABLE')",
            name="ck_evidence_state",
        ),
        CheckConstraint("version > 0", name="ck_evidence_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    evidence_key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    state: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))
    value: Mapped[dict] = mapped_column(JSON)
    reviewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    media_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id"), nullable=True)
    locators: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EvidenceSnapshot(Base):
    __tablename__ = "evidence_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    evidence_ids: Mapped[list] = mapped_column(JSON)
    facts: Mapped[dict] = mapped_column(JSON)
    unknowns: Mapped[list] = mapped_column(JSON)
    contradictions: Mapped[list] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
