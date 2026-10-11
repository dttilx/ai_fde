import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.diagnosis.ledger import BudgetLedger
from app.diagnosis.models import DiagnosisRun, PendingHumanAction
from app.incidents.models import EvidenceSnapshot
from app.shared.db import session_factory
from app.shared.jobs.models import Job
from tests.acceptance.test_a203 import create, execute


def answer(client, run_id, answers, endpoint="information", fresh_process=False):
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    payload = {
        "type": "INFORMATION",
        "interrupt_id": cp["interrupt_id"],
        "expected_checkpoint_version": cp["checkpoint_version"],
        "idempotency_key": uuid4().hex,
        "answers": answers,
    }
    result = client.post(f"/api/diagnoses/{run_id}/{endpoint}", json=payload)
    assert result.status_code == 200, result.text
    assert client.post(f"/api/diagnoses/{run_id}/{endpoint}", json=payload).status_code == 409
    if fresh_process:
        processed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from tests.acceptance.test_a203 import execute; execute(sys.argv[1])",
                result.json()["job_id"],
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert processed.returncode == 0, processed.stderr
    else:
        execute(result.json()["job_id"])
    return client.get(f"/api/diagnoses/{run_id}").json()


def test_three_source_bound_questions_partial_resume_and_auto_report():
    client, started = create(description="A310，似乎漏气")
    run_id = started["diagnosis_run_id"]
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert cp["interrupt_type"] == "INFORMATION"
    assert set(cp["pending_questions"]) == {
        "upstream_pressure_mpa",
        "device_pressure_mpa",
        "continuous_leak_sound",
    }
    assert len(cp["question_details"]) == 3
    assert all(q["citation_ids"] and q["source_ref"] == "A310" for q in cp["question_details"])
    with session_factory()() as db:
        job = db.get(Job, started["job_id"])
        assert job.status == "SUCCEEDED" and job.result_kind == "PAUSED"
        assert job.lease_until is None
        original = db.get(DiagnosisRun, run_id).snapshot_id
    partial = answer(client, run_id, {"upstream_pressure_mpa": 0.64})
    assert partial["state"] == "NEEDS_INFORMATION" and partial["report"] is None
    cp2 = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert set(cp2["pending_questions"]) == {"device_pressure_mpa", "continuous_leak_sound"}
    assert cp2["counters"]["distinct_questions"] == 3
    final = answer(
        client,
        run_id,
        {"device_pressure_mpa": 0.41, "continuous_leak_sound": True},
        fresh_process=True,
    )
    assert final["state"] == "COMPLETED", final
    report = final["report"]
    assert report["release_mode"] == "AUTO_VALIDATED"
    assert all(c["status"] == "POSSIBLE" for c in report["possible_causes"])
    assert "接头松动" not in str(report["known_facts"])
    assert [s["alarm_step_ref"] for s in report["check_sequence"]] == [
        f"A310:STEP{i}" for i in range(1, 5)
    ]
    assert all(s["citation_ids"] for s in report["check_sequence"] + report["safety_preconditions"])
    cp3 = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert cp3["graph_thread_id"] == run_id
    assert cp3["counters"]["resumes"] == 2
    assert cp3["counters"]["steps"] > cp["counters"]["steps"]
    with session_factory()() as db:
        assert "upstream_pressure_mpa" not in db.get(EvidenceSnapshot, original).facts
        questions = db.scalars(
            select(PendingHumanAction).where(
                PendingHumanAction.run_id == run_id, PendingHumanAction.kind == "INFORMATION"
            )
        ).all()
        assert sorted(len(q.reasons) for q in questions) == [2, 3]


def test_smoke_in_resumed_observation_stops_before_any_new_retrieval():
    client, started = create(description="A310")
    run_id = started["diagnosis_run_id"]
    before = client.get(f"/api/diagnoses/{run_id}").json()
    stopped = answer(client, run_id, {"smoke": True})
    assert stopped["state"] == "WAITING_EXPERT" and stopped["report"] is None
    assert sum(n["node"] == "retrieve" for n in stopped["timeline"]) == sum(
        n["node"] == "retrieve" for n in before["timeline"]
    )


def test_force_review_and_non_reference_readings_do_not_auto_release():
    for force, pressure in ((True, 0.41), (False, 0.52)):
        client, started = create(force=force, description="A310")
        final = answer(
            client,
            started["diagnosis_run_id"],
            {
                "upstream_pressure_mpa": 0.64,
                "device_pressure_mpa": pressure,
                "continuous_leak_sound": True,
            },
        )
        assert final["state"] == "FINALIZING", final
        assert final["report"]["release_mode"] == "PENDING_REVIEW"
        assert final["report"]["publication_status"] == "DRAFT"


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_untyped_leak_answer_is_rejected_without_new_evidence(value):
    client, started = create(description="A310")
    run_id = started["diagnosis_run_id"]
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    response = client.post(
        f"/api/diagnoses/{run_id}/information",
        json={
            "type": "INFORMATION",
            "interrupt_id": cp["interrupt_id"],
            "expected_checkpoint_version": cp["checkpoint_version"],
            "idempotency_key": uuid4().hex,
            "answers": {"continuous_leak_sound": value},
        },
    )
    assert response.status_code == 422
    assert (
        client.get(f"/api/diagnoses/{run_id}/checkpoint").json()["checkpoint_version"]
        == cp["checkpoint_version"]
    )


def test_resume_allowance_exhaustion_does_not_reset_thread_or_enqueue():
    client, started = create(description="A310")
    run_id = started["diagnosis_run_id"]
    with session_factory()() as db, db.begin():
        run = db.get(DiagnosisRun, run_id)
        ledger = db.get(BudgetLedger, run.ledger_id)
        ledger.counters = {**ledger.counters, "resumes": 5}
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    rejected = client.post(
        f"/api/diagnoses/{run_id}/information",
        json={
            "type": "INFORMATION",
            "interrupt_id": cp["interrupt_id"],
            "expected_checkpoint_version": cp["checkpoint_version"],
            "idempotency_key": uuid4().hex,
            "answers": {"upstream_pressure_mpa": 0.64},
        },
    )
    assert rejected.status_code == 409
    assert client.get(f"/api/diagnoses/{run_id}/checkpoint").json()["graph_thread_id"] == run_id
