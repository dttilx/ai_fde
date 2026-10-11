"""Named integrity gate for append-only evidence and report versions."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from app.diagnosis.models import ReportVersion
from app.feedback.models import RepairOutcome
from app.incidents.models import Evidence, EvidenceSnapshot
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create
from tests.integration import test_diagnosis_persistence as persistence

pytest_plugins = ["tests.integration.test_diagnosis_persistence"]


def test_evidence_and_reports_cannot_be_overwritten(runs):
    for model in (ReportVersion, Evidence, EvidenceSnapshot):
        persistence.test_original_reports_and_evidence_are_database_append_only(runs, model)


def test_report_revisions_keep_original_version(runs):
    persistence.test_one_thread_retains_multiple_immutable_versions(runs)


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_repair_outcomes_are_append_only(operation):
    client, started = create()
    state = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    response = client.post(
        f"/api/incidents/{state['incident_id']}/repair-outcomes",
        json={
            "diagnosis_run_id": started["diagnosis_run_id"],
            "report_version_id": state["report"]["report_version_id"],
            "repair_action": "尚未维修，等待授权复核",
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 200, response.text
    assert response.json()["validation_status"] == "UNVERIFIED"
    row_id = response.json()["repair_outcome_id"]
    with session_factory()() as db:
        row = db.get(RepairOutcome, row_id)
        if operation == "UPDATE":
            row.repair_action = "未经授权的覆盖尝试"
        else:
            db.delete(row)
        with pytest.raises(DBAPIError, match="APPEND_ONLY_RECORD"):
            db.flush()
        db.rollback()
        assert db.get(RepairOutcome, row_id).repair_action == "尚未维修，等待授权复核"
