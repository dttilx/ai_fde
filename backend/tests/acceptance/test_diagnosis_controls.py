from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import func, select

from app.diagnosis.models import DiagnosisRun, ReportVersion, ResumeRequest
from app.shared.db import session_factory
from app.shared.jobs.models import Job
from tests.acceptance.test_a203 import create, execute
from tests.acceptance.test_resource_access import fixture_client


def review_request(client, run_id):
    state = client.get(f"/api/diagnoses/{run_id}").json()
    checkpoint = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    return {
        "type": "REPORT_REVIEW",
        "interrupt_id": checkpoint["interrupt_id"],
        "expected_checkpoint_version": checkpoint["checkpoint_version"],
        "idempotency_key": uuid4().hex,
        "report_version_id": state["report"]["report_version_id"],
        "report_hash": state["report_hash"],
    }


def effect_counts(run_id):
    with session_factory()() as db:
        run = db.get(DiagnosisRun, run_id)
        jobs = db.scalar(
            select(func.count()).select_from(Job).where(Job.resource_id == run.incident_id)
        )
        reports = db.scalar(
            select(func.count()).select_from(ReportVersion).where(ReportVersion.run_id == run_id)
        )
        resumes = db.scalar(
            select(func.count()).select_from(ResumeRequest).where(ResumeRequest.run_id == run_id)
        )
        return jobs, reports, resumes


def test_stale_or_wrong_report_resume_has_no_effects():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    body = review_request(client, run_id)
    before = effect_counts(run_id)
    for replacement in (
        {"expected_checkpoint_version": body["expected_checkpoint_version"] - 1},
        {"report_hash": "wrong"},
        {"interrupt_id": "wrong"},
        {"report_version_id": str(uuid4())},
    ):
        response = client.post(f"/api/diagnoses/{run_id}/resume", json={**body, **replacement})
        assert response.status_code == 409, response.text
        assert effect_counts(run_id) == before
    assert client.get(f"/api/diagnoses/{run_id}/checkpoint").json()["counters"]["resumes"] == 0


def test_concurrent_resume_enqueues_exactly_one_segment_and_publishes_once():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    body = review_request(client, run_id)
    before = effect_counts(run_id)
    other = fixture_client("engineer")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                c.post,
                f"/api/diagnoses/{run_id}/resume",
                json={**body, "idempotency_key": uuid4().hex},
            )
            for c in (client, other)
        ]
        responses = [future.result(timeout=15) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    accepted = next(response for response in responses if response.status_code == 200)
    assert effect_counts(run_id) == (before[0] + 1, before[1], before[2] + 1)
    execute(accepted.json()["job_id"])
    assert effect_counts(run_id) == (before[0] + 1, before[1] + 1, before[2] + 1)
    state = client.get(f"/api/diagnoses/{run_id}").json()
    assert state["state"] == "COMPLETED"
    assert client.get(f"/api/diagnoses/{run_id}/checkpoint").json()["counters"]["resumes"] == 1


def test_cancel_paused_graph_preserves_draft_and_cannot_resume():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    body = review_request(client, run_id)
    job_id = started["job_id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "SUCCEEDED" and job["result_kind"] == "PAUSED"
    before = effect_counts(run_id)
    response = client.post(
        f"/api/jobs/{job_id}/cancel",
        json={"expected_status_version": job["status_version"]},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 200, response.text
    state = client.get(f"/api/diagnoses/{run_id}").json()
    assert state["state"] == "FAILED" and state["failure_reason"] == "USER_CANCELLED"
    assert state["report_hash"] == body["report_hash"]
    assert state["report"]["publication_status"] == "DRAFT"
    assert client.post(f"/api/diagnoses/{run_id}/resume", json=body).status_code == 409
    assert effect_counts(run_id) == before


def test_foreign_business_expert_cannot_access_or_resume_engineer_run():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    body = review_request(client, run_id)
    before = effect_counts(run_id)
    expert = fixture_client("expert")
    for path in (
        f"/api/diagnoses/{run_id}",
        f"/api/diagnoses/{run_id}/checkpoint",
        f"/api/jobs/{started['job_id']}",
        f"/api/diagnoses/{run_id}/retrieval-assessments",
    ):
        assert expert.get(path).status_code == 404
    assert expert.post(f"/api/diagnoses/{run_id}/resume", json=body).status_code == 404
    assert effect_counts(run_id) == before
