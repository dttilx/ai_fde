import asyncio
import time
from uuid import uuid4

from sqlalchemy import select

from app.diagnosis.models import DiagnosisRun, ReportVersion
from app.diagnosis.service import execute_diagnosis
from app.shared.db import session_factory
from app.shared.jobs.executor import ExecutorRegistry
from app.shared.jobs.models import Job
from app.shared.jobs.worker import Worker
from tests.acceptance.test_resource_access import fixture_client


def execute(job_id):
    registry = ExecutorRegistry()
    registry.register("DIAGNOSIS", execute_diagnosis)
    worker = Worker(registry, timeout=120)
    for _ in range(200):
        with session_factory()() as db:
            job = db.get(Job, job_id)
            if job.status in {"SUCCEEDED", "FAILED", "TIMED_OUT"}:
                assert job.status == "SUCCEEDED", job.error_code
                return
        if not asyncio.run(worker.run_once()):
            time.sleep(0.05)
    raise AssertionError("job not processed")


def create(force=False, description="A203，设定165，实际128，加热电流0，已预热"):
    client = fixture_client("engineer")
    incident = client.post(
        "/api/incidents",
        json={"raw_description": description},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert incident.status_code == 200
    started = client.post(
        f"/api/incidents/{incident.json()['incident_id']}/diagnoses",
        json={"force_review": force},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert started.status_code == 200, started.text
    execute(started.json()["job_id"])
    return client, started.json()


def test_a203_report_safe_order_sources_and_private_assessment():
    client, started = create()
    run = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    assert run["state"] == "COMPLETED", run
    report = run["report"]
    assert report["release_mode"] == "AUTO_VALIDATED"
    assert report["possible_causes"][0]["status"] == "POSSIBLE"
    refs = {row["source_ref"] for row in report["evidence_sources"]}
    assert {"A203", "H02", "WO-240-042", "SAFE-02"}.issubset(refs)
    nodes = [row["node"] for row in run["timeline"]]
    assert nodes.index("safety_gate") < nodes.index("retrieve")
    for area in ("possible_causes", "safety_preconditions", "check_sequence"):
        assert all(row["citation_ids"] for row in report[area])
    assert all(not q["blocking"] for q in report["missing_information"])
    assessments = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}/retrieval-assessments")
    assert assessments.json()["status"] == "SKIPPED_POLICY"


def test_a203_checkpoint_review_resume_and_duplicate_guard():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    state = client.get(f"/api/diagnoses/{run_id}").json()
    assert state["report"]["publication_status"] == "DRAFT"
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert cp["interrupt_type"] == "REPORT_REVIEW"
    body = {
        "type": "REPORT_REVIEW",
        "interrupt_id": cp["interrupt_id"],
        "expected_checkpoint_version": cp["checkpoint_version"],
        "idempotency_key": uuid4().hex,
        "report_version_id": state["report"]["report_version_id"],
        "report_hash": state["report_hash"],
    }
    resumed = client.post(f"/api/diagnoses/{run_id}/resume", json=body)
    assert resumed.status_code == 200, resumed.text
    assert client.post(f"/api/diagnoses/{run_id}/resume", json=body).status_code == 409
    execute(resumed.json()["job_id"])
    final = client.get(f"/api/diagnoses/{run_id}").json()
    assert final["state"] == "COMPLETED", final
    assert final["report"]["release_mode"] == "HUMAN_REVIEWED"
    with session_factory()() as db:
        run = db.get(DiagnosisRun, run_id)
        assert run.graph_thread_id == run_id
        versions = db.scalars(select(ReportVersion).where(ReportVersion.run_id == run_id)).all()
        assert len(versions) == 2
        assert versions[0].content_hash != versions[1].content_hash


def test_information_resume_preserves_run_and_accumulated_budget():
    client, started = create(description="A203")
    run_id = started["diagnosis_run_id"]
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert cp["interrupt_type"] == "INFORMATION"
    body = {
        "type": "INFORMATION",
        "interrupt_id": cp["interrupt_id"],
        "expected_checkpoint_version": cp["checkpoint_version"],
        "idempotency_key": uuid4().hex,
        "answers": {
            "set_temperature_c": 165,
            "actual_temperature_c": 128,
            "heating_current_a": 0,
            "preheating_confirmed": True,
        },
    }
    resumed = client.post(f"/api/diagnoses/{run_id}/resume", json=body)
    assert resumed.status_code == 200, resumed.text
    execute(resumed.json()["job_id"])
    final = client.get(f"/api/diagnoses/{run_id}").json()
    assert final["state"] == "COMPLETED", final
    after = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert after["counters"]["steps"] > cp["counters"]["steps"]
    assert after["counters"]["resumes"] == 1
    assert after["graph_thread_id"] == run_id


def test_danger_and_contradictions_block_ordinary_retrieval():
    for description in (
        "A203，设定165，实际128，电流0，已预热，出现焦味",
        "A203，设定165，实际128，实际160，电流0，已预热",
    ):
        client, started = create(description=description)
        run = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
        assert run["state"] in {"WAITING_EXPERT", "CONFLICT_BLOCKED"}
        assert run["report"] is None
        assert "retrieve" not in [n["node"] for n in run["timeline"]]


def test_invalid_form_does_not_hide_textual_emergency():
    client = fixture_client("engineer")
    response = client.post(
        "/api/incidents",
        json={"raw_description": "现场出现焦味", "observations": {"smoke": "yes"}},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 422
    assert response.json()["immediate_safety_notice"]["safety_blocked"]
