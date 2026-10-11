from uuid import uuid4

from sqlalchemy import select

from app.diagnosis.models import ReportVersion
from app.knowledge.assessment_models import ClaimReview
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create, execute


def get_run(client, run_id):
    return client.get(f"/api/diagnoses/{run_id}").json()


def test_non_template_atomic_claim_review_and_publication():
    client, started = create(description="A203，设定165，实际130，加热电流0，已预热")
    run_id = started["diagnosis_run_id"]
    run = get_run(client, run_id)
    assert run["claim_review_required"]
    checkpoint = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    resume = {
        "type": "REPORT_REVIEW",
        "interrupt_id": checkpoint["interrupt_id"],
        "expected_checkpoint_version": checkpoint["checkpoint_version"],
        "idempotency_key": uuid4().hex,
        "report_version_id": run["report"]["report_version_id"],
        "report_hash": run["report_hash"],
    }
    assert client.post(f"/api/diagnoses/{run_id}/resume", json=resume).status_code == 409
    decisions = [
        {
            "claim_id": item["claim_id"],
            "claim_hash": item["claim_hash"],
            "decision": "ACCEPT",
            "note": "测试：已逐项核对当前读数与引用，仅接受可能原因和安全建议。",
            "verified_source_refs": item["citation_ids"],
        }
        for item in run["claim_review_items"]
    ]
    body = {
        "report_version_id": resume["report_version_id"],
        "report_hash": resume["report_hash"],
        "decisions": decisions,
    }
    invalid = {**body, "decisions": [*decisions[:-1], {**decisions[-1], "claim_hash": "wrong"}]}
    assert (
        client.post(
            f"/api/diagnoses/{run_id}/claim-reviews/batch",
            json=invalid,
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 409
    )
    with session_factory()() as db:
        assert not db.scalars(select(ClaimReview).where(ClaimReview.run_id == run_id)).all()
    key = uuid4().hex
    reviewed = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch", json=body, headers={"Idempotency-Key": key}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert (
        client.post(
            f"/api/diagnoses/{run_id}/claim-reviews/batch",
            json=body,
            headers={"Idempotency-Key": key},
        ).status_code
        == 409
    )
    resumed = client.post(
        f"/api/diagnoses/{run_id}/resume",
        json={**resume, "claim_review_ids": reviewed.json()["review_ids"]},
    )
    assert resumed.status_code == 200, resumed.text
    execute(resumed.json()["job_id"])
    final = get_run(client, run_id)
    assert final["state"] == "COMPLETED", final
    assert final["report"]["release_mode"] == "HUMAN_REVIEWED"
    assert final["report"]["claim_review_ids"] == reviewed.json()["review_ids"]


def test_claim_correction_preserves_old_draft_and_invalidates_reviews():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    old = get_run(client, run_id)
    from app.diagnosis.claim_review import material_claims
    from app.shared.versioning import content_hash

    claim_id, claim = next(iter(material_claims(old["report"]).items()))
    body = {
        "report_version_id": old["report"]["report_version_id"],
        "report_hash": old["report_hash"],
        "decisions": [
            {
                "claim_id": claim_id,
                "claim_hash": content_hash(claim),
                "decision": "CORRECT",
                "note": "修订措辞，仍为可能原因。",
                "verified_source_refs": claim["citation_ids"],
                "correction": "H1 加热回路可能开路，尚未完成授权检查",
            }
        ],
    }
    result = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=body,
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert result.status_code == 200, result.text
    new = get_run(client, run_id)
    assert new["report_hash"] != old["report_hash"]
    assert new["claim_review_required"]
    with session_factory()() as db:
        versions = db.scalars(select(ReportVersion).where(ReportVersion.run_id == run_id)).all()
        assert len(versions) == 2
        assert (
            db.get(ReportVersion, old["report"]["report_version_id"]).content_hash
            == old["report_hash"]
        )
