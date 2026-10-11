from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.access.models import new_id, now
from app.shared.db import Base


class RetrievalAssessment(Base):
    __tablename__ = "retrieval_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=now, nullable=True
    )
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_profile_records.id"), nullable=True
    )
    receipt_id: Mapped[str | None] = mapped_column(
        ForeignKey("egress_receipt_records.id"), nullable=True
    )


class ProviderProfileRecord(Base):
    __tablename__ = "provider_profile_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EgressReceiptRecord(Base):
    __tablename__ = "egress_receipt_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    profile_id: Mapped[str] = mapped_column(ForeignKey("provider_profile_records.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AssessmentCache(Base):
    __tablename__ = "assessment_cache"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"))
    scope_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClaimReview(Base):
    __tablename__ = "claim_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    report_id: Mapped[str] = mapped_column(ForeignKey("report_versions.id"))
    actor_id: Mapped[str] = mapped_column(String(36))
    report_hash: Mapped[str] = mapped_column(String(64))
    claim_id: Mapped[str] = mapped_column(String(100))
    claim_hash: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)


class CitationAssessment(Base):
    __tablename__ = "citation_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    claim_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
