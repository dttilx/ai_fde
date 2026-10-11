from uuid import uuid4

import pytest
from sqlalchemy import select

from app.diagnosis.checkpoints import checkpoint_store, initialize_checkpoints
from app.diagnosis.graph import build_graph
from app.diagnosis.ledger import LIMITS, BudgetLedger, CallReservation, reserve
from app.shared.db import session_factory
from app.shared.errors import DomainError


@pytest.mark.parametrize("metric,limit", LIMITS.items())
def test_exact_limit_survives_new_session_and_overflow_has_no_side_effect(metric, limit):
    ledger_id, first, denied = str(uuid4()), uuid4().hex, uuid4().hex
    with session_factory()() as db, db.begin():
        db.add(BudgetLedger(id=ledger_id, counters={}))
        db.flush()
        reserve(db, ledger_id, first, {metric: limit})
    with session_factory()() as db, db.begin():
        ledger = db.get(BudgetLedger, ledger_id)
        version = ledger.version
        with pytest.raises(DomainError, match="BUDGET_EXHAUSTED"):
            reserve(db, ledger_id, denied, {metric: 1})
        assert ledger.counters[metric] == limit
        assert ledger.version == version
        assert db.get(CallReservation, denied) is None
        with pytest.raises(DomainError, match="RESERVATION_ALREADY_EXISTS"):
            reserve(db, ledger_id, first, {metric: 0})


def test_retrieval_loop_rechecks_safety_and_fails_before_fourth_tool():
    initialize_checkpoints()
    thread, ledger_id = str(uuid4()), str(uuid4())
    with session_factory()() as db, db.begin():
        db.add(BudgetLedger(id=ledger_id, counters={}))
    calls = []

    def safety(state):
        calls.append("safety")
        return {"status": "SAFETY_CHECK", "safety": {"safety_blocked": False}}

    def retrieval(state):
        with session_factory()() as db, db.begin():
            reserve(db, ledger_id, uuid4().hex, {"retrievals": 1, "tools": 1})
        calls.append("retrieve")
        return {"status": "RETRIEVING"}

    with checkpoint_store() as store:
        graph = build_graph(
            store,
            {
                "safety_gate": safety,
                "retrieve": retrieval,
                "decide": lambda state: {"status": "RETRIEVING"},
            },
        )
        with pytest.raises(DomainError, match="BUDGET_EXHAUSTED"):
            graph.invoke(
                {"facts": {}}, {"configurable": {"thread_id": thread}, "recursion_limit": 32}
            )
    assert calls == ["safety", "retrieve"] * 3 + ["safety"]
    with session_factory()() as db:
        assert db.get(BudgetLedger, ledger_id).counters == {"retrievals": 3, "tools": 3}
        assert (
            len(
                db.scalars(
                    select(CallReservation).where(CallReservation.ledger_id == ledger_id)
                ).all()
            )
            == 3
        )


def test_late_citation_conflict_routes_to_expert_and_preserves_draft(monkeypatch):
    from app.diagnosis import claim_support
    from tests.acceptance.test_a203 import create

    # Test control injects a semantic contradiction; it does not replace a success result.
    monkeypatch.setattr(claim_support, "conflicting_claims", lambda db, report: {"CAUSE-1"})
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    result = client.get(f"/api/diagnoses/{run_id}").json()
    assert result["state"] == "CONFLICT_BLOCKED", result
    assert result["report"]["publication_status"] == "WITHHELD"
    assert result["report"]["check_sequence"] == []
    assert result["report"]["possible_causes"] == []
    assert result["report"]["immediate_safety_actions"][0]["citation_ids"]
    checkpoint = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert checkpoint["interrupt_type"] == "EXPERT"
    assert result["timeline"][-1]["node"] == "expert_review"


def test_support_stage_failure_never_exposes_published_report(monkeypatch):
    from app.diagnosis import claim_support
    from tests.acceptance.test_a203 import execute
    from tests.acceptance.test_resource_access import fixture_client

    async def failure(*args, **kwargs):
        raise DomainError("CLAIM_STAGE_FAILURE", 409)

    monkeypatch.setattr(claim_support, "assess_support", failure)
    client = fixture_client("engineer")
    incident = client.post(
        "/api/incidents",
        json={"raw_description": "A203，设定165，实际128，加热电流0，已预热"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert incident.status_code == 200
    started = client.post(
        f"/api/incidents/{incident.json()['incident_id']}/diagnoses",
        json={},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert started.status_code == 200, started.text
    # Worker exposes its sanitized failure code; the run retains the precise domain code.
    with pytest.raises(AssertionError, match="EXECUTION_FAILED"):
        execute(started.json()["job_id"])
    result = client.get(f"/api/diagnoses/{started.json()['diagnosis_run_id']}").json()
    assert result["state"] == "FAILED"
    assert result["failure_reason"] == "CLAIM_STAGE_FAILURE"
    assert result["report"]["publication_status"] == "DRAFT"
    assert result["report"]["release_mode"] == "PENDING_REVIEW"


def test_missing_required_knowledge_escalates_without_inventing_report(monkeypatch):
    from app.diagnosis import nodes
    from tests.acceptance.test_a203 import create

    original = nodes.retrieve

    def without_case(*args, **kwargs):
        return [row for row in original(*args, **kwargs) if row["source_key"] != "H02"]

    monkeypatch.setattr(nodes, "retrieve", without_case)
    client, started = create()
    result = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    assert result["state"] == "WAITING_EXPERT", result
    assert result["report"] is None
    checkpoint = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}/checkpoint").json()
    assert checkpoint["interrupt_type"] == "EXPERT"
    assert result["timeline"][-1]["node"] == "expert_review"
