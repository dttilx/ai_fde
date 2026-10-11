import asyncio
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select

from app.access.models import now
from app.shared.db import session_factory
from app.shared.jobs.executor import ExecutorRegistry, JobTicket
from app.shared.jobs.models import Job
from app.shared.jobs.service import transition


class Worker:
    def __init__(self, registry: ExecutorRegistry, timeout: float = 30):
        self.registry = registry
        self.timeout = timeout
        self.owner = str(uuid4())

    def reconcile_expired(self) -> int:
        with session_factory()() as db, db.begin():
            jobs = db.scalars(
                select(Job)
                .where(Job.status == "RUNNING", Job.lease_until < now())
                .with_for_update(skip_locked=True)
            ).all()
            for job in jobs:
                job.fence += 1
                transition(db, job, "FAILED")
                job.error_code = "WORKER_LEASE_EXPIRED"
                job.owner = None
                job.lease_until = None
            return len(jobs)

    async def run_once(self) -> bool:
        with session_factory()() as db, db.begin():
            job = db.scalar(
                select(Job)
                .where(
                    Job.status.in_(["QUEUED", "RETRY_WAIT"]),
                    or_(Job.retry_at.is_(None), Job.retry_at <= now()),
                    Job.kind.in_(list(self.registry.handlers)),
                )
                .order_by(Job.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return False
            job.fence += 1
            job.attempt += 1
            job.owner = self.owner
            job.deadline_at = now() + timedelta(seconds=self.timeout)
            job.lease_until = job.deadline_at + timedelta(seconds=5)
            transition(db, job, "RUNNING")
            ticket = JobTicket(job.id, job.resource_id, job.actor_id, job.fence, job.payload)
            kind = job.kind
        result = None
        error = None
        interrupted = False
        try:
            result = await asyncio.wait_for(self.registry.execute(kind, ticket), self.timeout)
            if result.result_kind == "PAUSED" and kind != "DIAGNOSIS":
                raise RuntimeError("INVALID_PAUSED_JOB_KIND")
            target = "SUCCEEDED"
        except TimeoutError:
            result = None
            target, error = "TIMED_OUT", "EXECUTION_TIMEOUT"
        except asyncio.CancelledError:
            interrupted = True
            result = None
            target, error = "CANCELLED", "WORKER_CANCELLED"
        except Exception:
            result = None
            target, error = "FAILED", "EXECUTION_FAILED"
        with session_factory()() as db, db.begin():
            job = db.get(Job, ticket.job_id, with_for_update=True)
            if job is None or job.status != "RUNNING" or job.fence != ticket.fence:
                if interrupted:
                    raise asyncio.CancelledError
                return True  # cancelled/reconciled work cannot commit late output.
            transition(db, job, target)
            job.owner = None
            job.lease_until = None
            job.error_code = error
            if result is not None:
                job.result, job.result_kind = result.data, result.result_kind
        if interrupted:
            raise asyncio.CancelledError
        return True
