from uuid import uuid4

import pytest

from app.shared.db import session_factory
from app.shared.errors import DomainError
from app.shared.invocations import checkpoint_reconciled, commit_effect, reserve_effect
from app.shared.jobs.models import Job
from app.shared.jobs.service import cancel_job, create_job, transition


def test_effect_replay_fencing_and_checkpoint_mismatch():
    key, run_id = uuid4().hex, str(uuid4())
    with session_factory()() as db, db.begin():
        job = create_job(db, run_id, "fixture", "DIAGNOSIS", uuid4().hex, {})
        job.fence = 1
        transition(db, job, "RUNNING")
        db.flush()
        job_id = job.id
        assert reserve_effect(db, job_id, 1, key, run_id) is None
        commit_effect(db, job_id, 1, key, {"report_ref": "fixture"}, "checkpoint-1")
    with session_factory()() as db, db.begin():
        assert reserve_effect(db, job_id, 1, key, run_id) == {"report_ref": "fixture"}
        assert not checkpoint_reconciled(db, key, "different-checkpoint")
        assert checkpoint_reconciled(db, key, "checkpoint-1")
        cancel_job(db, db.get(Job, job_id, with_for_update=True))
    with session_factory()() as db, db.begin():
        with pytest.raises(DomainError):
            reserve_effect(db, job_id, 1, uuid4().hex, run_id)
