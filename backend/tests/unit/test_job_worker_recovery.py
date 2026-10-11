import asyncio

from app.shared.jobs.executor import ExecutionResult, ExecutorRegistry
from app.shared.jobs.worker import Worker
from tests.contract.test_job_status import new_job, read_job


async def test_worker_fences_late_result_after_cancellation():
    registry = ExecutorRegistry()
    release = asyncio.Event()

    async def delayed(ticket):
        await release.wait()
        return ExecutionResult("COMPLETED", {"must_not_commit": True})

    registry.register("QR", delayed)
    job = new_job()
    task = asyncio.create_task(Worker(registry).run_once())
    while read_job(job.id).status != "RUNNING":
        await asyncio.sleep(0.01)
    from app.shared.db import session_factory
    from app.shared.jobs.service import cancel_job

    with session_factory()() as db, db.begin():
        cancel_job(db, db.get(type(job), job.id, with_for_update=True))
    release.set()
    await task
    assert read_job(job.id).status == "CANCELLED" and read_job(job.id).result is None
