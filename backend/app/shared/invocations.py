from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.access.models import now
from app.shared.db import Base
from app.shared.errors import DomainError
from app.shared.jobs.models import Job


class Invocation(Base):
    __tablename__ = "invocations"
    effect_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(30), default="RESERVED")
    fence: Mapped[int] = mapped_column(Integer)
    checkpoint_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Outbox(Base):
    __tablename__ = "outbox"
    effect_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON)
    delivered: Mapped[int] = mapped_column(Integer, default=0)


def assert_fence(db: Session, job_id: str, fence: int) -> None:
    job = db.get(Job, job_id, with_for_update=True, populate_existing=True)
    if not job or job.status != "RUNNING" or job.fence != fence:
        raise DomainError("INVOCATION_FENCED", 409)
    if job.deadline_at and job.deadline_at <= now():
        raise DomainError("EXECUTION_TIMEOUT", 409)


def reserve_effect(db: Session, job_id: str, fence: int, key: str, run_id: str) -> dict | None:
    assert_fence(db, job_id, fence)
    existing = db.get(Invocation, key, with_for_update=True)
    if existing:
        if existing.status == "COMMITTED":
            return existing.output
        raise DomainError("EFFECT_REQUIRES_RECONCILIATION", 409)
    db.add(Invocation(effect_key=key, run_id=run_id, fence=fence))
    db.flush()
    return None


def commit_effect(
    db: Session, job_id: str, fence: int, key: str, output: dict, checkpoint_ref: str | None = None
) -> None:
    assert_fence(db, job_id, fence)
    invocation = db.get(Invocation, key, with_for_update=True)
    if not invocation or invocation.status != "RESERVED" or invocation.fence != fence:
        raise DomainError("EFFECT_ALREADY_COMMITTED_OR_FENCED", 409)
    invocation.output = output
    invocation.checkpoint_ref = checkpoint_ref
    invocation.status = "COMMITTED"
    db.add(Outbox(effect_key=key, run_id=invocation.run_id, payload=output))


def checkpoint_reconciled(db: Session, key: str, persisted_checkpoint_ref: str | None) -> bool:
    """Caller obtains the reference from PostgresSaver, never from user input.

    A missing/mismatched checkpoint keeps the effect pending delivery; no speculative replay.
    """
    invocation = db.get(Invocation, key)
    return bool(
        invocation
        and invocation.status == "COMMITTED"
        and invocation.checkpoint_ref is not None
        and invocation.checkpoint_ref == persisted_checkpoint_ref
    )
