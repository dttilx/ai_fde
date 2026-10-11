from uuid import uuid4

from sqlalchemy import select

from app.diagnosis.models import ReportVersion
from app.knowledge.assessment_models import CitationAssessment, ClaimReview
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create


def review_body(run, decision="ACCEPT"):
    return {
        "report_version_id": run["report"]["report_version_id"],
        "report_hash": run["report_hash"],
        "decisions": [
            {
                "claim_id": item["claim_id"],
                "claim_hash": item["claim_hash"],
                "decision": decision,
                "note": "模拟逐项核对来源，仅接受建议。",
                "verified_source_refs": item["citation_ids"],
            }
            for item in run["claim_review_items"]
        ],
    }


def test_citation_assessment_distinguishes_template_from_unknown_support():
    client, started = create()
    response = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}/citation-assessments")
    assert response.status_code == 200, response.text
    assert response.json()["assessments"]
    assert all(
        row["mode"] == "RULE" and not row["review_required"]
        for row in response.json()["assessments"]
    )
    client, started = create(description="A203，设定165，实际130，加热电流0，已预热")
    response = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}/citation-assessments")
    assert response.status_code == 200
    assert all(
        row["relation"] == "UNKNOWN" and row["review_required"]
        for row in response.json()["assessments"]
    )
    assert all(row["mode"] != "REAL_JEV" for row in response.json()["assessments"])


def test_extraneous_review_id_cannot_be_used_as_a_complete_review_set():
    client, started = create(description="A203，设定165，实际130，加热电流0，已预热")
    run_id = started["diagnosis_run_id"]
    run = client.get(f"/api/diagnoses/{run_id}").json()
    response = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=review_body(run),
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 200
    from app.diagnosis.claim_review import accepted_reviews

    with session_factory()() as db:
        report = db.get(ReportVersion, run["report"]["report_version_id"])
        actor_id = db.scalar(select(ClaimReview.actor_id).where(ClaimReview.report_id == report.id))
        assert not accepted_reviews(
            db, report, actor_id, [*response.json()["review_ids"], uuid4().hex]
        )


def test_final_root_cause_correction_cannot_pass_as_advisory_text():
    client, started = create(description="A203，设定165，实际130，加热电流0，已预热")
    run_id = started["diagnosis_run_id"]
    run = client.get(f"/api/diagnoses/{run_id}").json()
    body = review_body(run, "CORRECT")
    body["decisions"] = [{**body["decisions"][0], "correction": "最终根因为H1开路，可以复机"}]
    response = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=body,
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 409, response.text
    assert client.get(f"/api/diagnoses/{run_id}").json()["report_hash"] == run["report_hash"]


def test_changed_policy_invalidates_existing_review_without_creating_job():
    from app.access.models import PolicyBinding
    from app.diagnosis.models import DiagnosisRun
    from app.shared.jobs.models import Job

    client, started = create(description="A203，设定165，实际130，加热电流0，已预热")
    run_id = started["diagnosis_run_id"]
    run = client.get(f"/api/diagnoses/{run_id}").json()
    reviewed = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=review_body(run),
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert reviewed.status_code == 200, reviewed.text
    before = client.get(f"/api/diagnoses/{run_id}/citation-assessments").json()
    assert all(row["mode"] == "HUMAN" for row in before["assessments"])
    with session_factory()() as db, db.begin():
        incident_id = db.get(DiagnosisRun, run_id).incident_id
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "INCIDENT", PolicyBinding.resource_id == incident_id
            )
        )
        policy.version += 1
        old_jobs = list(db.scalars(select(Job.id).where(Job.resource_id == incident_id)))
    after = client.get(f"/api/diagnoses/{run_id}/citation-assessments").json()
    assert all(
        row["relation"] == "UNKNOWN" and row["review_required"] for row in after["assessments"]
    )
    checkpoint = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    response = client.post(
        f"/api/diagnoses/{run_id}/resume",
        json={
            "type": "REPORT_REVIEW",
            "interrupt_id": checkpoint["interrupt_id"],
            "expected_checkpoint_version": checkpoint["checkpoint_version"],
            "idempotency_key": uuid4().hex,
            "report_version_id": run["report"]["report_version_id"],
            "report_hash": run["report_hash"],
            "claim_review_ids": reviewed.json()["review_ids"],
        },
    )
    assert response.status_code == 409, response.text
    with session_factory()() as db:
        assert set(db.scalars(select(Job.id).where(Job.resource_id == incident_id))) == set(
            old_jobs
        )


def test_rejection_blocks_old_acceptance_and_assessment_is_append_only():
    from app.diagnosis.claim_review import accepted_reviews
    from tests.acceptance.test_resource_access import fixture_client

    client, started = create(description="A203，设定165，实际130，加热电流0，已预热")
    run_id = started["diagnosis_run_id"]
    run = client.get(f"/api/diagnoses/{run_id}").json()
    accepted = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=review_body(run),
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert accepted.status_code == 200
    rejected_body = review_body(run, "REJECT")
    rejected_body["decisions"] = rejected_body["decisions"][:1]
    rejected = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=rejected_body,
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert rejected.status_code == 200
    assessment = client.get(f"/api/diagnoses/{run_id}/citation-assessments").json()
    assert assessment["assessments"][0]["status"] == "REJECTED"
    assert (
        fixture_client("expert").get(f"/api/diagnoses/{run_id}/citation-assessments").status_code
        == 404
    )
    with session_factory()() as db:
        report = db.get(ReportVersion, run["report"]["report_version_id"])
        actor_id = db.scalar(select(ClaimReview.actor_id).where(ClaimReview.report_id == report.id))
        assert not accepted_reviews(db, report, actor_id, accepted.json()["review_ids"])
        records = db.scalars(
            select(CitationAssessment).where(CitationAssessment.run_id == run_id)
        ).all()
        assert any(row.payload["relation"] == "SUPPORTED" for row in records)
        assert any(row.payload["relation"] == "UNKNOWN" for row in records)


def test_corrected_draft_can_be_reviewed_and_published_without_mutating_original():
    from tests.acceptance.test_a203 import execute

    client, started = create(description="A203，设定165，实际130，加热电流0，已预热")
    run_id = started["diagnosis_run_id"]
    original = client.get(f"/api/diagnoses/{run_id}").json()
    body = review_body(original, "CORRECT")
    body["decisions"] = [{**body["decisions"][0], "correction": "H1回路可能开路，仍需授权人员核实"}]
    corrected = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=body,
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert corrected.status_code == 200, corrected.text
    draft = client.get(f"/api/diagnoses/{run_id}").json()
    accepted = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=review_body(draft),
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert accepted.status_code == 200, accepted.text
    checkpoint = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    response = client.post(
        f"/api/diagnoses/{run_id}/resume",
        json={
            "type": "REPORT_REVIEW",
            "interrupt_id": checkpoint["interrupt_id"],
            "expected_checkpoint_version": checkpoint["checkpoint_version"],
            "idempotency_key": uuid4().hex,
            "report_version_id": draft["report"]["report_version_id"],
            "report_hash": draft["report_hash"],
            "claim_review_ids": accepted.json()["review_ids"],
        },
    )
    assert response.status_code == 200, response.text
    execute(response.json()["job_id"])
    final = client.get(f"/api/diagnoses/{run_id}").json()
    assert final["state"] == "COMPLETED", final
    assert final["report"]["possible_causes"][0]["cause"] == body["decisions"][0]["correction"]
    assert all(
        row["mode"] == "HUMAN"
        for row in client.get(f"/api/diagnoses/{run_id}/citation-assessments").json()["assessments"]
    )
    with session_factory()() as db:
        assert (
            db.get(ReportVersion, original["report"]["report_version_id"]).content_hash
            == original["report_hash"]
        )
        assert (
            len(db.scalars(select(ReportVersion).where(ReportVersion.run_id == run_id)).all()) == 3
        )


def test_individual_review_is_shown_without_waiving_other_claims():
    client, started = create(description="A203，设定165，实际130，加热电流0，已预热")
    run_id = started["diagnosis_run_id"]
    run = client.get(f"/api/diagnoses/{run_id}").json()
    body = review_body(run)
    claim_id = body["decisions"][0]["claim_id"]
    body["decisions"] = body["decisions"][:1]
    reviewed = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=body,
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert reviewed.status_code == 200
    rows = client.get(f"/api/diagnoses/{run_id}/citation-assessments").json()["assessments"]
    assert next(row for row in rows if row["claim_id"] == claim_id)["mode"] == "HUMAN"
    assert all(row["review_required"] for row in rows if row["claim_id"] != claim_id)
