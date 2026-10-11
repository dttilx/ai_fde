import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding
from app.diagnosis.auto_repair import repair_once
from app.diagnosis.claim_support import assess_support, conflicting_claims
from app.diagnosis.ledger import BudgetLedger, CallReservation
from app.diagnosis.models import DiagnosisRun, ReportVersion
from app.diagnosis.report import validate_report
from app.diagnosis.retrieval_context import citations
from app.knowledge.assessment_models import CitationAssessment
from app.knowledge.models import SourceRecord
from app.shared.db import session_factory
from app.shared.errors import DomainError
from app.shared.providers.jev import FixtureJevClaimEvaluator, JevClaimEvaluation, JevClaimJudgment
from app.shared.versioning import content_hash

pytest_plugins = ["tests.integration.test_jev_stage"]


@pytest.fixture
def claim_simulation(simulation):
    admin, run_id, ledger_id, sources = simulation
    chosen = sources[:2]
    with Session(admin) as db, db.begin():
        run = db.get(DiagnosisRun, run_id)
        original = db.get(ReportVersion, run.report_version_id)
        source_ids = [item["source_id"] for item in chosen]
        for policy in db.scalars(
            select(PolicyBinding).where(
                (
                    (PolicyBinding.resource_type == "SOURCE")
                    & PolicyBinding.resource_id.in_(source_ids)
                )
                | (
                    (PolicyBinding.resource_type == "INCIDENT")
                    & (PolicyBinding.resource_id == run.incident_id)
                )
            )
        ):
            policy.approved_purposes = ["PASSAGE_RELEVANCE", "CLAIM_SUPPORT"]
            policy.version += 1
        citation_payloads = citations(
            db,
            [
                {
                    "source_id": row.id,
                    "checksum": row.checksum,
                    "release_id": row.release_id,
                    "content": row.content,
                    "locator": row.locator,
                    "collection": row.collection,
                }
                for row in db.scalars(select(SourceRecord).where(SourceRecord.id.in_(source_ids)))
            ],
        )
        payload = deepcopy(original.payload)
        payload.update(
            report_version_id=str(uuid4()),
            release_decision_id=str(uuid4()),
            evidence_sources=citation_payloads,
            validation_check_ids=[],
            release_mode="PENDING_REVIEW",
            publication_status="DRAFT",
            status="FINALIZING",
        )
        for area in (
            "manual_references",
            "safety_preconditions",
            "check_sequence",
            "stop_conditions",
            "immediate_safety_actions",
            "escalation_reasons",
        ):
            payload[area] = []
        payload["possible_causes"] = payload["possible_causes"][:1]
        payload["possible_causes"][0].update(
            cause="Possible circuit interruption; not confirmed.",
            citation_ids=[row["citation_id"] for row in citation_payloads],
        )
        validate_report(payload)
        db.add(
            ReportVersion(
                id=payload["report_version_id"],
                run_id=run_id,
                parent_id=original.id,
                payload=payload,
                content_hash=content_hash(payload),
                manifest={**original.manifest, "self_authored_test": True},
            )
        )
        run.report_version_id = payload["report_version_id"]
        report_id = payload["report_version_id"]
    return admin, run_id, ledger_id, report_id, source_ids


class ScriptedClaimFixture:
    model = "fixture-jev_claim-v1"
    mode = "FIXTURE"

    def __init__(self, relation="UNKNOWN", actual_model=None):
        self.relation, self.actual_model = relation, actual_model or self.model
        self.calls = []

    async def evaluate(self, payload):
        self.calls.append(payload)
        return JevClaimEvaluation(
            JevClaimJudgment(relation=self.relation), self.actual_model, "FIXTURE", 0
        )


def test_permitted_claim_fixture_minimal_set_and_replay_once(claim_simulation):
    _, run_id, ledger_id, report_id, _ = claim_simulation
    provider = ScriptedClaimFixture()
    ids = asyncio.run(assess_support(run_id, report_id, evaluator=provider))
    assert len(provider.calls) == 1
    assert len(provider.calls[0]["state"]["sources"]) == 2
    assert set(provider.calls[0]["questions"]) == {"support_relation"}
    assert "report_version_id" not in str(provider.calls)
    assert asyncio.run(assess_support(run_id, report_id, evaluator=provider)) == ids
    assert len(provider.calls) == 1
    with session_factory()() as db:
        row = db.get(CitationAssessment, ids[0])
        assert row.payload["status"] == "FIXTURE"
        assert row.payload["support_relation"] == "UNKNOWN"
        assert row.payload["review_required"]
        reservation = db.get(CallReservation, row.payload["reservation_ids"][0])
        assert reservation.status == "SETTLED" and reservation.actual_tokens == 0
        assert db.get(BudgetLedger, ledger_id).counters["tools"] >= 2


def test_supported_fixture_does_not_approve_free_generated_claim(claim_simulation):
    _, run_id, _, report_id, _ = claim_simulation
    ids = asyncio.run(assess_support(run_id, report_id, evaluator=ScriptedClaimFixture("SUPPORTS")))
    with session_factory()() as db:
        row = db.get(CitationAssessment, ids[0])
        assert row.payload["support_relation"] == "SUPPORTS"
        assert row.payload["relation"] == "UNKNOWN" and row.payload["review_required"]


def test_cited_set_permission_denial_prevents_transport(claim_simulation):
    admin, run_id, _, report_id, source_ids = claim_simulation
    with Session(admin) as db, db.begin():
        policy = db.scalar(select(PolicyBinding).where(PolicyBinding.resource_id == source_ids[-1]))
        policy.egress = "DENY"
        policy.version += 1
    provider = ScriptedClaimFixture()
    ids = asyncio.run(assess_support(run_id, report_id, evaluator=provider))
    assert provider.calls == []
    with session_factory()() as db:
        assert db.get(CitationAssessment, ids[0]).payload["status"] == "SKIPPED_POLICY"


def test_wrong_actual_model_not_semantic_success(claim_simulation):
    _, run_id, _, report_id, _ = claim_simulation
    ids = asyncio.run(
        assess_support(run_id, report_id, evaluator=ScriptedClaimFixture(actual_model="other"))
    )
    with session_factory()() as db:
        row = db.get(CitationAssessment, ids[0])
        assert row.payload["status"] == "UNAVAILABLE"
        assert row.payload["actual_model"] is None and row.payload["support_relation"] == "UNKNOWN"


def test_repair_is_one_withdrawal_not_root_replacement_and_preserves_history(claim_simulation):
    _, run_id, ledger_id, report_id, _ = claim_simulation
    ids = asyncio.run(
        assess_support(run_id, report_id, evaluator=ScriptedClaimFixture("UNSUPPORTED"))
    )
    changed_id = repair_once(run_id, report_id, ids)
    assert changed_id and changed_id != report_id
    with session_factory()() as db:
        old, changed = db.get(ReportVersion, report_id), db.get(ReportVersion, changed_id)
        assert (
            old.payload["possible_causes"][0]["cause"]
            == "Possible circuit interruption; not confirmed."
        )
        assert changed.parent_id == old.id
        assert "无法判断" in changed.payload["possible_causes"][0]["cause"]
        assert changed.payload["publication_status"] == "DRAFT"
        assert changed.payload["release_mode"] == "PENDING_REVIEW"
        assert changed.payload["claim_review_ids"] == []
        assert db.get(CallReservation, f"auto-repair:{ledger_id}").status == "SETTLED"
    new_ids = asyncio.run(
        assess_support(run_id, changed_id, evaluator=ScriptedClaimFixture("UNSUPPORTED"))
    )
    assert repair_once(run_id, changed_id, new_ids) is None


def test_revocation_after_judgment_blocks_repair(claim_simulation):
    admin, run_id, _, report_id, source_ids = claim_simulation
    ids = asyncio.run(
        assess_support(run_id, report_id, evaluator=ScriptedClaimFixture("UNSUPPORTED"))
    )
    with Session(admin) as db, db.begin():
        policy = db.scalar(select(PolicyBinding).where(PolicyBinding.resource_id == source_ids[-1]))
        policy.egress = "DENY"
        policy.version += 1
    with pytest.raises(DomainError, match="PROCESSING_PERMISSION_CHANGED"):
        repair_once(run_id, report_id, ids)


def test_default_claim_fixture_is_unknown_not_success(claim_simulation):
    _, run_id, _, report_id, _ = claim_simulation
    ids = asyncio.run(assess_support(run_id, report_id, evaluator=FixtureJevClaimEvaluator()))
    with session_factory()() as db:
        row = db.get(CitationAssessment, ids[0])
        assert row.payload["processing_mode"] == "FIXTURE"
        assert row.payload["support_relation"] == "UNKNOWN"


def test_conflict_cannot_be_accepted_or_corrected_by_unqualified_role(claim_simulation):
    from tests.acceptance.test_resource_access import fixture_client

    _, run_id, _, report_id, _ = claim_simulation
    asyncio.run(assess_support(run_id, report_id, evaluator=ScriptedClaimFixture("CONTRADICTS")))
    client = fixture_client("engineer")
    run = client.get(f"/api/diagnoses/{run_id}").json()
    item = run["claim_review_items"][0]
    body = {
        "report_version_id": report_id,
        "report_hash": run["report_hash"],
        "decisions": [
            {
                "claim_id": item["claim_id"],
                "claim_hash": item["claim_hash"],
                "decision": "ACCEPT",
                "note": "模拟审核",
                "verified_source_refs": item["citation_ids"],
            }
        ],
    }
    rejected = client.post(
        f"/api/diagnoses/{run_id}/claim-reviews/batch",
        json=body,
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert (
        rejected.status_code == 409
        and rejected.json()["code"] == "CLAIM_CONFLICT_REQUIRES_RESOLUTION"
    )
    body["decisions"][0].update(
        decision="CORRECT", correction="Possible fault, needs verification."
    )
    assert (
        client.post(
            f"/api/diagnoses/{run_id}/claim-reviews/batch",
            json=body,
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 403
    )


def test_natural_permission_expiry_does_not_reuse_judgment(claim_simulation, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    _, run_id, _, report_id, _ = claim_simulation
    provider = ScriptedClaimFixture("SUPPORTS")
    first = asyncio.run(assess_support(run_id, report_id, evaluator=provider))
    monkeypatch.setattr(
        "app.shared.providers.egress.datetime",
        SimpleNamespace(now=lambda zone: datetime.now(UTC) + timedelta(days=2)),
    )
    second = asyncio.run(assess_support(run_id, report_id, evaluator=provider))
    assert second != first and len(provider.calls) == 1
    with session_factory()() as db:
        assert db.get(CitationAssessment, second[0]).payload["status"] == "SKIPPED_POLICY"


def test_revoked_permission_removes_old_conflict_from_decision_but_keeps_audit(claim_simulation):
    admin, run_id, _, report_id, sources = claim_simulation
    ids = asyncio.run(
        assess_support(run_id, report_id, evaluator=ScriptedClaimFixture("CONTRADICTS"))
    )
    with session_factory()() as db:
        assert conflicting_claims(db, db.get(ReportVersion, report_id))
    with Session(admin) as db, db.begin():
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "SOURCE", PolicyBinding.resource_id == sources[1]
            )
        )
        policy.egress = "DENY"
        policy.version += 1
    with session_factory()() as db:
        assert conflicting_claims(db, db.get(ReportVersion, report_id)) == set()
        assert db.get(CitationAssessment, ids[0]).payload["support_relation"] == "CONTRADICTS"
