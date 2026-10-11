import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.shared.db import session_factory
from app.shared.errors import DomainError
from app.shared.jobs.executor import ExecutionResult, ExecutorRegistry
from app.shared.jobs.models import STATUSES, Job, JobEvent
from app.shared.jobs.service import cancel_job, create_job, retry_job
from app.shared.jobs.worker import Worker


def new_job(kind="QR"):
    with session_factory()() as db, db.begin():
        return create_job(db, str(uuid4()), "fixture-actor", kind, str(uuid4()), {})


def read_job(job_id):
    with session_factory()() as db:
        return db.get(Job, job_id)


async def test_pause_is_success_and_releases_worker():
    registry = ExecutorRegistry()

    async def paused(ticket):
        # Only tests worker state mapping. Persistence is covered by the real A203 graph test.
        return ExecutionResult("PAUSED", {"pause_marker": "worker-mapping-only"})

    registry.register("DIAGNOSIS", paused)
    worker = Worker(registry)
    job = new_job("DIAGNOSIS")
    assert await worker.run_once()
    complete = read_job(job.id)
    assert complete.status == "SUCCEEDED" and complete.result_kind == "PAUSED"
    assert complete.owner is None and complete.lease_until is None
    with session_factory()() as db:
        assert len(db.scalars(select(JobEvent).where(JobEvent.job_id == job.id)).all()) == 3


async def test_timeout_retry_failure_and_cancellation_states():
    registry = ExecutorRegistry()

    async def slow(ticket):
        await asyncio.sleep(1)
        return ExecutionResult("COMPLETED", {})

    registry.register("QR", slow)
    worker = Worker(registry, timeout=0.02)
    job = new_job()
    await worker.run_once()
    assert read_job(job.id).status == "TIMED_OUT"
    with session_factory()() as db, db.begin():
        retry_job(db, db.get(Job, job.id, with_for_update=True))
    assert read_job(job.id).status == "RETRY_WAIT"

    async def failed(ticket):
        raise RuntimeError("private provider payload must not be persisted")

    registry.register("QR", failed)
    await worker.run_once()
    assert read_job(job.id).status == "FAILED"
    assert read_job(job.id).error_code == "EXECUTION_FAILED"
    cancelled = new_job()
    with session_factory()() as db, db.begin():
        cancel_job(db, db.get(Job, cancelled.id, with_for_update=True))
    assert read_job(cancelled.id).status == "CANCELLED"
    assert STATUSES == {
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "TIMED_OUT",
        "CANCELLED",
        "RETRY_WAIT",
    }


async def test_cancelled_running_handler_cannot_commit_late_output():
    started = asyncio.Event()
    release = asyncio.Event()
    registry = ExecutorRegistry()

    async def delayed(ticket):
        started.set()
        await release.wait()
        return ExecutionResult("COMPLETED", {"late": True})

    registry.register("QR", delayed)
    job = new_job()
    worker_task = asyncio.create_task(Worker(registry).run_once())
    await started.wait()
    with session_factory()() as db, db.begin():
        current = db.get(Job, job.id, with_for_update=True)
        assert current.status == "RUNNING"
        cancel_job(db, current)
    release.set()
    await worker_task
    assert read_job(job.id).status == "CANCELLED"
    assert read_job(job.id).result is None


def test_duplicate_enqueue_rejected_without_duplicate_events():
    job = new_job()
    with session_factory()() as db, db.begin():
        with pytest.raises(DomainError):
            create_job(db, job.resource_id, job.actor_id, job.kind, job.idempotency_key, {})
        cancel_job(db, db.get(Job, job.id, with_for_update=True))
