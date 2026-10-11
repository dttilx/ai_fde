from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant, User
from app.diagnosis.ledger import BudgetLedger
from app.diagnosis.models import DiagnosisRun, LinkedRun
from app.knowledge.models import SourceRecord
from app.shared.config import settings
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create, execute
from tests.acceptance.test_resource_access import fixture_client


@pytest.fixture
def extension():
    engineer, started = create(force=True)
    admin = create_engine(settings().migration_database_url.get_secret_value())
    with Session(admin) as db, db.begin():
        parent = db.get(DiagnosisRun, started["diagnosis_run_id"])
        expert = db.scalar(select(User).where(User.username == "expert"))
        original = db.scalar(select(SourceRecord).where(SourceRecord.source_key == "A203"))
        private = SourceRecord(
            release_id=original.release_id,
            source_key="LINK-" + uuid4().hex,
            collection="MANUAL",
            content="Self-authored private reference.",
            checksum=sha256(b"Self-authored private reference.").hexdigest(),
            locator={"page": 1, "section": "SIMULATION"},
            metadata_fields={},
        )
        db.add(private)
        db.flush()
        db.add(ResourceGrant(user_id=expert.id, resource_type="SOURCE", resource_id=private.id))
        db.add(
            PolicyBinding(
                resource_type="SOURCE",
                resource_id=private.id,
                readable_by=[expert.id],
                egress="DENY",
                origin="SELF_AUTHORED_SIMULATION",
                classification="TECHNICAL_REFERENCE",
            )
        )
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "INCIDENT",
                PolicyBinding.resource_id == parent.incident_id,
            )
        )
        policy.readable_by = [*policy.readable_by, expert.id]
        # The parent run may carry a broad source scope after earlier tests.
        # Grant the fixture expert the parent's already-visible sources so a
        # full-suite run tests scope expansion, rather than stale test data
        # leaking as an unrelated 404. Production ACLs remain unchanged.
        parent_sources = list(parent.source_scope)
        for source_row in db.scalars(
            select(SourceRecord).where(SourceRecord.id.in_(parent_sources))
        ):
            source_policy = db.scalar(
                select(PolicyBinding).where(
                    PolicyBinding.resource_type == "SOURCE",
                    PolicyBinding.resource_id == source_row.id,
                )
            )
            if source_policy and expert.id not in source_policy.readable_by:
                source_policy.readable_by = [*source_policy.readable_by, expert.id]
            if not db.scalar(
                select(ResourceGrant).where(
                    ResourceGrant.user_id == expert.id,
                    ResourceGrant.resource_type == "SOURCE",
                    ResourceGrant.resource_id == source_row.id,
                )
            ):
                db.add(
                    ResourceGrant(
                        user_id=expert.id,
                        resource_type="SOURCE",
                        resource_id=source_row.id,
                    )
                )
        db.add(
            ResourceGrant(
                user_id=expert.id,
                resource_type="INCIDENT",
                resource_id=parent.incident_id,
                permission="WRITE",
            )
        )
        source_id, parent_id = private.id, parent.id
        scope, ledger_id = [*parent.source_scope, private.id], parent.ledger_id
    try:
        yield engineer, fixture_client("expert"), parent_id, scope, ledger_id
    finally:
        with Session(admin) as db, db.begin():
            for grant in db.scalars(
                select(ResourceGrant).where(
                    ResourceGrant.resource_type == "SOURCE", ResourceGrant.resource_id == source_id
                )
            ):
                grant.active = False
        admin.dispose()


def submit(expert, parent, scope, key=None):
    return expert.post(
        f"/api/diagnoses/{parent}/linked-runs",
        json={"source_scope": scope, "reason": "核实专家可读的补充资料"},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def test_extension_uses_new_thread_shared_budget_and_does_not_leak_to_engineer(extension):
    engineer, expert, parent, scope, ledger_id = extension
    before = expert.get(f"/api/diagnoses/{parent}/checkpoint").json()["counters"]
    key = uuid4().hex
    response = submit(expert, parent, scope, key)
    assert response.status_code == 200, response.text
    child = response.json()
    assert child["diagnosis_run_id"] != parent
    assert child["graph_thread_id"] == child["diagnosis_run_id"]
    assert submit(expert, parent, scope, key).status_code == 409
    for endpoint in (
        f"/api/diagnoses/{child['diagnosis_run_id']}",
        f"/api/diagnoses/{child['diagnosis_run_id']}/checkpoint",
        f"/api/jobs/{child['job_id']}",
    ):
        assert engineer.get(endpoint).status_code == 404
    denied_cancel = engineer.post(
        f"/api/jobs/{child['job_id']}/cancel",
        json={"expected_status_version": 0},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert denied_cancel.status_code == 404
    execute(child["job_id"])
    state = expert.get(f"/api/diagnoses/{child['diagnosis_run_id']}").json()
    assert state["state"] == "FINALIZING", state
    with session_factory()() as db:
        run = db.get(DiagnosisRun, child["diagnosis_run_id"])
        assert run.ledger_id == ledger_id
        assert db.get(BudgetLedger, ledger_id).counters["steps"] > before["steps"]
        assert db.get(BudgetLedger, ledger_id).counters["resumes"] == before["resumes"] + 1
        assert (
            len(db.scalars(select(LinkedRun).where(LinkedRun.parent_run_id == parent)).all()) == 1
        )


def test_extension_requires_expert_current_scope_and_actual_expansion(extension):
    engineer, expert, parent, scope, _ = extension
    assert submit(engineer, parent, scope).status_code == 403
    assert submit(expert, parent, scope[:-1]).status_code == 409
    assert submit(expert, parent, [*scope, str(uuid4())]).status_code == 404


def test_extension_cannot_reset_exhausted_resume_allowance(extension):
    _, expert, parent, scope, ledger_id = extension
    with session_factory()() as db, db.begin():
        ledger = db.get(BudgetLedger, ledger_id)
        ledger.counters = {**ledger.counters, "resumes": 5}
    response = submit(expert, parent, scope)
    assert response.status_code == 409 and response.json()["code"] == "BUDGET_EXHAUSTED"
    with session_factory()() as db:
        assert not db.scalars(select(LinkedRun).where(LinkedRun.parent_run_id == parent)).all()
