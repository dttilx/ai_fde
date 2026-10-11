from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access.models import now
from app.shared.errors import DomainError
from app.shared.jobs.models import KINDS, Job, JobEvent

ALLOWED = {
    "QUEUED": {"RUNNING", "CANCELLED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "RETRY_WAIT"},
    "FAILED": {"RETRY_WAIT"},
    "TIMED_OUT": {"RETRY_WAIT"},
    "RETRY_WAIT": {"RUNNING", "CANCELLED"},
    "SUCCEEDED": set(),
    "CANCELLED": set(),
}


def transition(db: Session, job: Job, target: str) -> None:
    if target not in ALLOWED[job.status]:
        raise DomainError("INVALID_JOB_TRANSITION", 409)
    job.status = target
    job.updated_at = now()
    db.add(JobEvent(job_id=job.id, status=target, fence=job.fence))


def create_job(
    db: Session,
    resource_id: str,
    actor_id: str,
    kind: str,
    key: str,
    payload: dict,
    parent: str | None = None,
) -> Job:
    if kind not in KINDS or not key or len(key) > 100:
        raise DomainError("INVALID_JOB_INPUT")
    job = Job(
        resource_id=resource_id,
        actor_id=actor_id,
        kind=kind,
        idempotency_key=key,
        payload=payload,
        parent_job_id=parent,
        deadline_at=now() + timedelta(seconds=120),
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
            db.add(JobEvent(job_id=job.id, status="QUEUED", fence=0))
    except IntegrityError:
        raise DomainError("DUPLICATE_SUBMISSION", 409) from None
    return job


def cancel_job(db: Session, job: Job) -> None:
    job.fence += 1
    transition(db, job, "CANCELLED")
    job.owner = None
    job.lease_until = None


def retry_job(db: Session, job: Job, delay: float = 0) -> None:
    if job.attempt >= 3:
        raise DomainError("RETRY_EXHAUSTED", 409)
    job.fence += 1
    transition(db, job, "RETRY_WAIT")
    # A zero-delay retry must be immediately eligible. Leaving a freshly
    # generated timestamp in the database can be fractionally in the future
    # under PostgreSQL clock precision, making the worker miss the first poll.
    job.retry_at = now() + timedelta(seconds=delay) if delay else None
    job.owner = None
    job.lease_until = None
