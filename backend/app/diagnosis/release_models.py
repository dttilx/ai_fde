from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.access.models import new_id
from app.shared.db import Base


class ReportReleaseDecision(Base):
    __tablename__ = "report_release_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_hash: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON)


class ValidationProof(Base):
    __tablename__ = "validation_proofs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_hash: Mapped[str] = mapped_column(String(64))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    template_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
