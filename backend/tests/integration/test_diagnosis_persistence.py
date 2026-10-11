"""Direct PostgreSQL rejection tests: application validation cannot hide a broken constraint."""

from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.diagnosis.models import Citation, DiagnosisRun, PendingHumanAction, ReportVersion
from app.incidents.models import Evidence, EvidenceSnapshot
from app.knowledge.models import KnowledgeRelease, SourceRecord
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create


@pytest.fixture(scope="module")
def runs():
    _, first = create(force=True)
    _, second = create(force=True)
    return first["diagnosis_run_id"], second["diagnosis_run_id"]


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("source_scope", [], "RUN_SCOPE_IMMUTABLE"),
        ("graph_thread_id", "another-thread", "RUN_SCOPE_IMMUTABLE"),
        ("actor_id", "another-actor", "RUN_SCOPE_IMMUTABLE"),
        ("actor_version", 99, "RUN_SCOPE_IMMUTABLE"),
        ("status", "UNRECOGNIZED", "run_status_valid"),
        ("checkpoint_version", 0, "CHECKPOINT_VERSION_INVALID"),
        ("checkpoint_version", 10000, "CHECKPOINT_VERSION_INVALID"),
    ],
)
def test_run_identity_scope_and_checkpoint_cannot_be_rewritten(runs, field, value, error):
    with session_factory()() as db:
        with pytest.raises(DBAPIError, match=error):
            db.execute(
                update(DiagnosisRun).where(DiagnosisRun.id == runs[0]).values({field: value})
            )
            db.flush()


def test_run_cannot_switch_ledger_or_incident_or_borrow_another_snapshot(runs):
    with session_factory()() as db:
        other = db.get(DiagnosisRun, runs[1])
        values = {
            "ledger_id": other.ledger_id,
            "incident_id": other.incident_id,
            "snapshot_id": other.snapshot_id,
        }
    for field, value in values.items():
        with session_factory()() as db:
            error = (
                "SNAPSHOT_INCIDENT_MISMATCH" if field == "snapshot_id" else "RUN_SCOPE_IMMUTABLE"
            )
            with pytest.raises(DBAPIError, match=error):
                db.execute(
                    update(DiagnosisRun).where(DiagnosisRun.id == runs[0]).values({field: value})
                )


def test_all_ten_states_are_valid_and_checkpoint_advances_one_at_a_time(runs):
    statuses = (
        "PREPARING",
        "SAFETY_CHECK",
        "RETRIEVING",
        "NEEDS_INFORMATION",
        "WAITING_EXPERT",
        "CONFLICT_BLOCKED",
        "FINALIZING",
        "COMPLETED",
        "ESCALATED",
        "FAILED",
    )
    with session_factory()() as db:
        run = db.get(DiagnosisRun, runs[0])
        before = run.checkpoint_version
        for status in statuses:
            run.status = status
            db.flush()
        run.checkpoint_version += 1
        db.flush()
        assert run.checkpoint_version == before + 1
        # Rollback keeps the live fixture paused and does not forge state transitions.


def test_citation_requires_actual_source_release_and_unique_identifier(runs):
    with session_factory()() as db:
        source = db.scalar(select(SourceRecord))
        other = KnowledgeRelease(release_key=uuid4().hex, source_checksum="a" * 64, config={})
        db.add(other)
        db.flush()
        db.add(Citation(id=uuid4().hex, source_id=source.id, release_id=other.id, payload={}))
        with pytest.raises(DBAPIError, match="CITATION_RELEASE_MISMATCH"):
            db.flush()
    with session_factory()() as db:
        existing = db.scalar(select(Citation))
        db.execute(
            Citation.__table__.insert().values(
                id=uuid4().hex,
                source_id=existing.source_id,
                release_id=existing.release_id,
                payload={},
            )
        )
        with pytest.raises(DBAPIError, match="citations_pkey"):
            db.execute(
                Citation.__table__.insert().values(
                    id=existing.id,
                    source_id=existing.source_id,
                    release_id=existing.release_id,
                    payload={},
                )
            )


@pytest.mark.parametrize("model", [ReportVersion, Evidence, EvidenceSnapshot])
def test_original_reports_and_evidence_are_database_append_only(runs, model):
    with session_factory()() as db:
        run = db.get(DiagnosisRun, runs[0])
        predicate = (
            model.run_id == run.id
            if model is ReportVersion
            else model.incident_id == run.incident_id
        )
        row = db.scalar(select(model).where(predicate))
        assert row is not None
        with pytest.raises(DBAPIError, match="APPEND_ONLY_RECORD"):
            db.execute(model.__table__.delete().where(model.id == row.id))


def test_one_thread_retains_multiple_immutable_versions(runs):
    with session_factory()() as db:
        run = db.get(DiagnosisRun, runs[0])
        original = db.get(ReportVersion, run.report_version_id)
        db.add(
            ReportVersion(
                run_id=run.id,
                parent_id=original.id,
                payload=original.payload,
                manifest=original.manifest,
                content_hash=original.content_hash,
            )
        )
        snapshot = db.get(EvidenceSnapshot, run.snapshot_id)
        db.add(
            EvidenceSnapshot(
                incident_id=run.incident_id,
                evidence_ids=snapshot.evidence_ids,
                facts=snapshot.facts,
                unknowns=snapshot.unknowns,
                contradictions=snapshot.contradictions,
                content_hash=snapshot.content_hash,
            )
        )
        db.flush()
        assert (
            len(db.scalars(select(ReportVersion).where(ReportVersion.run_id == run.id)).all()) >= 2
        )
        assert (
            len(
                db.scalars(
                    select(EvidenceSnapshot).where(EvidenceSnapshot.incident_id == run.incident_id)
                ).all()
            )
            >= 2
        )
        assert run.graph_thread_id == run.id


def test_pending_expert_action_is_deduplicated_and_preserves_original_reasons(runs):
    with session_factory()() as db:
        row = PendingHumanAction(
            run_id=runs[0], snapshot_hash=uuid4().hex, kind="EXPERT", reasons=["RISK_UNKNOWN"]
        )
        db.add(row)
        db.flush()
        row.assigned_actor_id = "fixture-expert"
        db.flush()
        row.reasons = ["CLEARED"]
        with pytest.raises(DBAPIError, match="HUMAN_ACTION_IMMUTABLE"):
            db.flush()
    with session_factory()() as db:
        snapshot_hash = uuid4().hex
        for _ in range(2):
            db.add(
                PendingHumanAction(
                    run_id=runs[0],
                    snapshot_hash=snapshot_hash,
                    kind="EXPERT",
                    reasons=["RISK_UNKNOWN"],
                )
            )
        with pytest.raises(DBAPIError, match="UniqueViolation|duplicate key"):
            db.flush()
