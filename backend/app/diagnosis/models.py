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
from app.shared.db import Base


class DiagnosisRun(Base):
    __tablename__ = "diagnosis_runs"
    __table_args__ = (CheckConstraint("graph_thread_id = id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_thread_id: Mapped[str] = mapped_column(String(36), unique=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    actor_id: Mapped[str] = mapped_column(String(36))
    actor_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="PREPARING")
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("evidence_snapshots.id"))
    source_scope: Mapped[list] = mapped_column(JSON)
    ledger_id: Mapped[str] = mapped_column(ForeignKey("budget_ledgers.id"))
    checkpoint_version: Mapped[int] = mapped_column(Integer, default=0)
    native_checkpoint_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    interrupt_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    interrupt_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    active_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    report_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    asked_fields: Mapped[list] = mapped_column(JSON, default=list)
    force_review: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LinkedRun(Base):
    __tablename__ = "linked_diagnosis_runs"
    __table_args__ = (UniqueConstraint("parent_run_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parent_run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    child_run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"), unique=True)
    actor_id: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(String(1000))
    idempotency_key: Mapped[str] = mapped_column(String(100))


class ReportVersion(Base):
    __tablename__ = "report_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    manifest: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20), default="AI")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Citation(Base):
    __tablename__ = "citations"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"))
    release_id: Mapped[str] = mapped_column(ForeignKey("knowledge_releases.id"))
    payload: Mapped[dict] = mapped_column(JSON)


class ResumeRequest(Base):
    __tablename__ = "resume_requests"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    actor_id: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    expected_version: Mapped[int] = mapped_column(Integer)
    interrupt_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    job_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PendingHumanAction(Base):
    __tablename__ = "pending_human_actions"
    __table_args__ = (UniqueConstraint("run_id", "snapshot_hash", "kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(30))
    reasons: Mapped[list] = mapped_column(JSON)
    assigned_actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class NodeAudit(Base):
    __tablename__ = "node_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("diagnosis_runs.id"))
    node_name: Mapped[str] = mapped_column(String(40))
    input_hash: Mapped[str] = mapped_column(String(64))
    output_status: Mapped[str] = mapped_column(String(30))
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
