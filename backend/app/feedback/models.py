from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.access.models import new_id, now
from app.shared.db import Base


class RepairOutcome(Base):
    __tablename__ = "repair_outcomes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    diagnosis_run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    report_version_id: Mapped[str] = mapped_column(String(36))
    supersedes_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_by: Mapped[str] = mapped_column(String(36))
    executor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confirmed_root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    repair_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    qualification_refs: Mapped[list] = mapped_column(JSON, default=list)
    restart_validation: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    restart_evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    validation_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CaseDraft(Base):
    __tablename__ = "case_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    repair_outcome_id: Mapped[str] = mapped_column(ForeignKey("repair_outcomes.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    assigned_reviewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    requested_scope: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deidentification_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VerifiedCase(Base):
    __tablename__ = "verified_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey("case_drafts.id"), unique=True)
    knowledge_release_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="APPROVED")
    approved_by: Mapped[str] = mapped_column(String(36))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
