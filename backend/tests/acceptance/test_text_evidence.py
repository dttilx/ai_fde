from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.incidents.models import Evidence, EvidenceSnapshot, Incident
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create
from tests.acceptance.test_resource_access import fixture_client


@pytest.mark.parametrize(
    "description",
    [
        "A203，设定165，实际128，电流0，可能已预热",
        "A203，设定165，上次实际128，电流0，已预热",
        "A203，设定165，实际128左右，电流0，已预热",
        "A203，设定165，实际128K，电流0，已预热",
        "A203，设定165，实际128，电流0mA，已预热",
    ],
)
def test_uncertain_current_evidence_never_receives_reference_auto_report(description):
    client, started = create(description=description)
    state = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    assert state["state"] == "NEEDS_INFORMATION", state
    assert state["report"] is None
    cp = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}/checkpoint").json()
    assert cp["interrupt_type"] == "INFORMATION" and cp["pending_questions"]


def test_raw_input_and_evidence_snapshot_are_append_only_and_sourced():
    client = fixture_client("engineer")
    description = "A203，实际128，可能是线路坏了"
    result = client.post(
        "/api/incidents",
        json={"raw_description": description},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert result.status_code == 200
    incident_id, snapshot_id = result.json()["incident_id"], result.json()["snapshot_id"]
    with session_factory()() as db:
        incident = db.get(Incident, incident_id)
        assert incident.raw_description == description
        snapshot = db.get(EvidenceSnapshot, snapshot_id)
        rows = db.scalars(select(Evidence).where(Evidence.id.in_(snapshot.evidence_ids))).all()
        assert rows and all(row.source == "TEXT" and row.state == "CONFIRMED" for row in rows)
        assert "root_cause" not in snapshot.facts
        assert snapshot.unknowns
        incident.raw_description = "overwritten"
        with pytest.raises(DBAPIError):
            db.flush()
        db.rollback()
        assert db.get(Incident, incident_id).raw_description == description
        snapshot = db.get(EvidenceSnapshot, snapshot_id)
        snapshot.facts = {"root_cause": "guessed"}
        with pytest.raises(DBAPIError):
            db.flush()
        db.rollback()
        assert "root_cause" not in db.get(EvidenceSnapshot, snapshot_id).facts


def test_invalid_evidence_state_is_rejected_by_database():
    client = fixture_client("engineer")
    created = client.post(
        "/api/incidents", json={"raw_description": "A203"}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert created.status_code == 200
    with session_factory()() as db:
        incident = db.get(Incident, created.json()["incident_id"])
        db.add(
            Evidence(
                incident_id=incident.id,
                evidence_key="invalid-state",
                state="AUTO_CONFIRMED",
                source="TEXT",
                value={"value": "bad"},
                reviewer_id=incident.owner_id,
            )
        )
        with pytest.raises(DBAPIError):
            db.flush()
        db.rollback()
        assert (
            db.scalar(
                select(Evidence).where(
                    Evidence.incident_id == incident.id, Evidence.evidence_key == "invalid-state"
                )
            )
            is None
        )
