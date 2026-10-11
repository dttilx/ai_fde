from uuid import uuid4

import pytest
from sqlalchemy import select

from app.diagnosis.models import DiagnosisRun, ReportVersion
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create


def test_current_facts_history_and_manual_are_separate_and_all_instructions_resolve():
    client, started = create()
    result = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    report = result["report"]
    assert result["state"] == "COMPLETED"
    assert report["publication_status"] == "PUBLISHED"
    assert "confidence" not in report
    assert any("128" in fact["text"] for fact in report["known_facts"])
    assert report["historical_comparisons"] and report["manual_references"]
    assert all(cause["status"] == "POSSIBLE" for cause in report["possible_causes"])
    assert [cause["rank"] for cause in report["possible_causes"]] == [1, 2, 3]
    refs = {citation["citation_id"] for citation in report["evidence_sources"]}
    for area in ("possible_causes", "safety_preconditions", "check_sequence", "stop_conditions"):
        for item in report[area]:
            assert item["citation_ids"] and set(item["citation_ids"]).issubset(refs)
    assert all(not row["blocking"] for row in report["missing_information"])
    with session_factory()() as db:
        versions = db.scalars(
            select(ReportVersion).where(ReportVersion.run_id == started["diagnosis_run_id"])
        ).all()
        assert len(versions) == 2
        draft = next(row for row in versions if row.payload["publication_status"] == "DRAFT")
        published = next(
            row for row in versions if row.payload["publication_status"] == "PUBLISHED"
        )
        assert published.parent_id == draft.id
        assert published.manifest["validated_draft_hash"] == draft.content_hash


@pytest.mark.parametrize(
    "description",
    [
        "A203，设定165，实际128，已预热",
        "A203，设定165，实际128，电流0，预热未知",
        "A203，设定165，实际128，电流1，已预热",
    ],
)
def test_missing_or_non_reference_facts_never_auto_release(description):
    client, started = create(description=description)
    result = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    assert result["state"] in {"NEEDS_INFORMATION", "FINALIZING"}
    if result["report"] is not None:
        assert result["report"]["release_mode"] == "PENDING_REVIEW"
        assert result["report"]["publication_status"] == "DRAFT"
    else:
        assert (
            client.get(f"/api/diagnoses/{started['diagnosis_run_id']}/checkpoint").json()[
                "interrupt_type"
            ]
            == "INFORMATION"
        )


def test_client_cannot_label_required_facts_optional_to_bypass_gate():
    client, started = create(description="A203")
    with session_factory()() as db:
        incident_id = db.get(DiagnosisRun, started["diagnosis_run_id"]).incident_id
        before = len(
            db.scalars(select(DiagnosisRun).where(DiagnosisRun.incident_id == incident_id)).all()
        )
    response = client.post(
        f"/api/incidents/{incident_id}/diagnoses",
        json={"force_review": False, "blocking": False},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 422
    with session_factory()() as db:
        assert (
            len(
                db.scalars(
                    select(DiagnosisRun).where(DiagnosisRun.incident_id == incident_id)
                ).all()
            )
            == before
        )
