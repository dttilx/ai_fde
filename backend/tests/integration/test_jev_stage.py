import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant, User
from app.diagnosis.ledger import BudgetLedger, CallReservation
from app.diagnosis.models import DiagnosisRun
from app.knowledge.assessment_models import (
    EgressReceiptRecord,
    ProviderProfileRecord,
    RetrievalAssessment,
)
from app.knowledge.models import KnowledgeRelease, SourceRecord
from app.knowledge.passage_assessment import assess_passages
from app.shared.config import settings
from app.shared.db import session_factory
from app.shared.errors import DomainError
from app.shared.providers.jev import JevEvaluation, JevJudgment
from tests.acceptance.test_a203 import create
from tests.acceptance.test_resource_access import fixture_client


@pytest.fixture
def simulation():
    admin = create_engine(settings().migration_database_url.get_secret_value())
    sources = []
    # Revoke leftovers from an interrupted prior fixture setup, never production sources.
    with Session(admin) as db, db.begin():
        stale = db.scalars(
            select(SourceRecord.id)
            .join(KnowledgeRelease)
            .where(
                SourceRecord.source_key.startswith("SIM-"),
                KnowledgeRelease.config["mode"].as_string() == "SELF_AUTHORED_SIMULATION",
            )
        ).all()
        for grant in db.scalars(
            select(ResourceGrant).where(
                ResourceGrant.resource_type == "SOURCE", ResourceGrant.resource_id.in_(stale)
            )
        ):
            grant.active = False
    with Session(admin) as db, db.begin():
        user = db.scalar(select(User).where(User.username == "engineer"))
        release = KnowledgeRelease(
            release_key=uuid4().hex,
            source_checksum="c" * 64,
            config={"mode": "SELF_AUTHORED_SIMULATION"},
        )
        db.add(release)
        db.flush()
        for index in range(10):
            excerpt = f"Self-authored packaging reference {index}; sample current reading is zero."
            record = SourceRecord(
                release_id=release.id,
                source_key="SIM-" + uuid4().hex,
                collection="MANUAL",
                content=excerpt,
                locator={"page": 1, "section": "SIMULATION"},
                checksum=sha256(excerpt.encode()).hexdigest(),
                metadata_fields={"approved_jev_excerpt": excerpt},
            )
            db.add(record)
            db.flush()
            db.add(ResourceGrant(user_id=user.id, resource_type="SOURCE", resource_id=record.id))
            db.add(
                PolicyBinding(
                    resource_type="SOURCE",
                    resource_id=record.id,
                    readable_by=[user.id],
                    origin="SELF_AUTHORED_SIMULATION",
                    classification="TECHNICAL_REFERENCE",
                    egress="APPROVED_REDACTED",
                    approved_providers=["jev"],
                    approved_purposes=["PASSAGE_RELEVANCE"],
                    basis="EXPLICIT_LOCAL_FIXTURE_TEST",
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            sources.append(
                {
                    "source_id": record.id,
                    "source_key": record.source_key,
                    "release_id": record.release_id,
                    "collection": record.collection,
                    "pinned": False,
                    "checksum": record.checksum,
                }
            )
    _, started = create(force=True)
    with Session(admin) as db, db.begin():
        run = db.get(DiagnosisRun, started["diagnosis_run_id"])
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "INCIDENT",
                PolicyBinding.resource_id == run.incident_id,
            )
        )
        policy.origin, policy.egress = "SELF_AUTHORED_SIMULATION", "APPROVED_REDACTED"
        policy.approved_providers, policy.approved_purposes = ["jev"], ["PASSAGE_RELEVANCE"]
        policy.basis, policy.expires_at = (
            "EXPLICIT_LOCAL_FIXTURE_TEST",
            datetime.now(UTC) + timedelta(days=1),
        )
        ledger_id = run.ledger_id
    run_id = started["diagnosis_run_id"]
    try:
        yield admin, run_id, ledger_id, sources
    finally:
        with Session(admin) as db, db.begin():
            identifiers = [source["source_id"] for source in sources]
            for grant in db.scalars(
                select(ResourceGrant).where(
                    ResourceGrant.resource_type == "SOURCE",
                    ResourceGrant.resource_id.in_(identifiers),
                )
            ):
                grant.active = False
            for policy in db.scalars(
                select(PolicyBinding).where(
                    PolicyBinding.resource_type == "SOURCE",
                    PolicyBinding.resource_id.in_(identifiers),
                )
            ):
                policy.egress, policy.readable_by = "DENY", []
                policy.version += 1


class TrackedFixture:
    mode = "FIXTURE"
    model = "scripted-fixture-v1"

    def __init__(self, *, delay=0.01, usage=0, bad_model=False, ledger_id=None):
        self.calls = self.active = self.peak = 0
        self.delay, self.usage, self.bad_model = delay, usage, bad_model
        self.inputs = []
        self.ledger_id = ledger_id

    async def evaluate(self, projection):
        if self.ledger_id:
            with session_factory()() as db:
                reservations = db.scalars(
                    select(CallReservation).where(
                        CallReservation.ledger_id == self.ledger_id,
                            CallReservation.status == "RESERVED",
                            CallReservation.amounts["tools"].as_integer() == 1,
                            CallReservation.amounts["tokens"].as_integer() > 0,
                    )
                ).all()
                assert reservations, "Budget must be committed before the provider starts"
                assert all(
                    row.amounts["tools"] == 1 and row.amounts["tokens"] > 0 for row in reservations
                )
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.inputs.append(projection)
        try:
            await asyncio.sleep(self.delay)
            return JevEvaluation(
                JevJudgment(),
                "wrong-model" if self.bad_model else self.model,
                "FIXTURE",
                self.usage,
            )
        finally:
            self.active -= 1


def test_allowed_fixture_has_receipts_minimal_inputs_and_durable_budget(simulation):
    _, run_id, ledger_id, sources = simulation
    provider = TrackedFixture(ledger_id=ledger_id)
    result = asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    assert result["status"] == "FIXTURE"
    assessment = result["assessments"][0]
    assert assessment["actual_model"] == provider.model
    assert assessment["relevance_level"] is None and assessment["route"] == "UNASSESSED"
    serialized = str(provider.inputs)
    assert sources[0]["source_id"] not in serialized and run_id not in serialized
    assert "WO-240-" not in serialized and "https://" not in serialized
    with session_factory()() as db:
        row = db.get(RetrievalAssessment, assessment["assessment_id"])
        assert row.provenance["attempts"] == 1
        receipt = db.get(EgressReceiptRecord, row.receipt_id)
        assert receipt.payload["decision"] == "ALLOWED"
        assert db.get(ProviderProfileRecord, row.profile_id).payload["external_transport"] is False
        reservation = db.get(CallReservation, row.provenance["reservation_ids"][0])
        assert reservation.status == "SETTLED" and reservation.actual_tokens == 0
        assert db.get(BudgetLedger, ledger_id).counters["tools"] == 2


def test_default_four_hard_eight_and_concurrency_two_are_real_limits(simulation):
    _, run_id, _, sources = simulation
    provider = TrackedFixture()
    result = asyncio.run(assess_passages(run_id, sources, 2, evaluator=provider))
    assert provider.calls == 4 and provider.peak == 2
    assert len(result["assessments"]) == 10
    assert sum(row["status"] == "SKIPPED_BUDGET" for row in result["assessments"]) == 6
    assert all(row["relevance_level"] is None for row in result["assessments"])
    provider = TrackedFixture()
    result = asyncio.run(assess_passages(run_id, sources, 3, evaluator=provider, limit=8))
    assert provider.calls == 6 and provider.peak <= 2  # First four reuse valid cache.
    with pytest.raises(DomainError, match="INVALID_ASSESSMENT_LIMIT"):
        asyncio.run(assess_passages(run_id, sources, 3, evaluator=provider, limit=9))


def test_cache_reuses_original_model_without_spending_again_then_policy_denies(simulation):
    admin, run_id, ledger_id, sources = simulation
    provider = TrackedFixture()
    first = asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    second = asyncio.run(assess_passages(run_id, sources[:1], 3, evaluator=provider))
    assert provider.calls == 1
    assert (
        second["status"] == "CACHED" and second["assessments"][0]["actual_model"] == provider.model
    )
    assert first["assessments"][0]["assessment_id"] != second["assessments"][0]["assessment_id"]
    with Session(admin) as db, db.begin():
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "SOURCE",
                PolicyBinding.resource_id == sources[0]["source_id"],
            )
        )
        policy.egress, policy.version = "DENY", policy.version + 1
    denied = asyncio.run(assess_passages(run_id, sources[:1], 3, evaluator=provider))
    assert denied["status"] == "SKIPPED_POLICY" and provider.calls == 1
    assert denied["assessments"][0]["actual_model"] is None
    with session_factory()() as db:
        assert db.get(BudgetLedger, ledger_id).counters["tools"] == 2


def test_read_access_revocation_blocks_even_cached_result(simulation):
    admin, run_id, _, sources = simulation
    provider = TrackedFixture()
    asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    with Session(admin) as db, db.begin():
        grant = db.scalar(
            select(ResourceGrant).where(
                ResourceGrant.resource_type == "SOURCE",
                ResourceGrant.resource_id == sources[0]["source_id"],
            )
        )
        grant.active = False
    with pytest.raises(DomainError, match="NOT_FOUND"):
        asyncio.run(assess_passages(run_id, sources[:1], 3, evaluator=provider))
    assert provider.calls == 1


def test_headroom_does_not_spend_last_six_calls(simulation):
    admin, run_id, ledger_id, sources = simulation
    with Session(admin) as db, db.begin():
        ledger = db.get(BudgetLedger, ledger_id)
        ledger.counters = {**ledger.counters, "tools": 14}
    provider = TrackedFixture()
    result = asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    assert result["status"] == "SKIPPED_BUDGET" and provider.calls == 0


def test_timeout_retries_once_and_unknown_usage_is_not_refunded(simulation):
    _, run_id, ledger_id, sources = simulation
    provider = TrackedFixture(delay=0.1)
    result = asyncio.run(
        assess_passages(run_id, sources[:1], 2, evaluator=provider, request_seconds=0.01)
    )
    assert provider.calls == 2 and result["status"] == "UNAVAILABLE"
    row_id = result["assessments"][0]["assessment_id"]
    with session_factory()() as db:
        record = db.get(RetrievalAssessment, row_id)
        reservations = [
            db.get(CallReservation, key) for key in record.provenance["reservation_ids"]
        ]
        assert all(row.status == "UNKNOWN" for row in reservations)
        assert db.get(BudgetLedger, ledger_id).counters["tokens"] == sum(
            row.amounts["tokens"] for row in reservations
        )
        assert record.payload["usage_state"] == "UNKNOWN"


def test_invalid_model_is_unavailable_without_retry_or_fabricated_score(simulation):
    _, run_id, _, sources = simulation
    provider = TrackedFixture(bad_model=True)
    result = asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    assert provider.calls == 1 and result["status"] == "UNAVAILABLE"
    assert result["assessments"][0]["actual_model"] is None
    assert result["assessments"][0]["relevance_level"] is None


def test_assessment_profile_and_receipt_are_append_only(simulation):
    _, run_id, _, sources = simulation
    result = asyncio.run(assess_passages(run_id, sources[:1], 2))
    with session_factory()() as db:
        row = db.get(RetrievalAssessment, result["assessments"][0]["assessment_id"])
        assert row.profile_id and row.receipt_id
        for model, identifier in (
            (RetrievalAssessment, row.id),
            (ProviderProfileRecord, row.profile_id),
            (EgressReceiptRecord, row.receipt_id),
        ):
            with pytest.raises(DBAPIError, match="APPEND_ONLY_RECORD"):
                with db.begin_nested():
                    db.execute(model.__table__.delete().where(model.id == identifier))


def test_api_shows_actual_latest_round_and_cache_status_not_a_constant(simulation):
    _, run_id, _, sources = simulation
    provider = TrackedFixture()
    asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    client = fixture_client("engineer")
    response = client.get(f"/api/diagnoses/{run_id}/retrieval-assessments")
    assert response.status_code == 200
    assert response.json()["retrieval_round"] == 2 and response.json()["status"] == "FIXTURE"
    asyncio.run(assess_passages(run_id, sources[:1], 3, evaluator=provider))
    asyncio.run(assess_passages(run_id, sources[:1], 3, evaluator=provider))
    payload = client.get(f"/api/diagnoses/{run_id}/retrieval-assessments").json()
    assert payload["retrieval_round"] == 3 and payload["status"] == "CACHED"
    assert len(payload["assessments"]) == 1
    assert "policy_hash" not in str(payload) and "profile_id" not in str(payload)
    denied = fixture_client("expert").get(f"/api/diagnoses/{run_id}/retrieval-assessments")
    assert denied.status_code == 404
    assert sources[0]["source_key"] not in denied.text


def test_two_calls_race_for_one_remaining_slot_without_spending_headroom(simulation):
    admin, run_id, ledger_id, sources = simulation
    with Session(admin) as db, db.begin():
        ledger = db.get(BudgetLedger, ledger_id)
        ledger.counters = {**ledger.counters, "tools": 13}
    provider = TrackedFixture()
    result = asyncio.run(assess_passages(run_id, sources[:2], 2, evaluator=provider))
    assert provider.calls == 1
    assert {row["status"] for row in result["assessments"]} == {"FIXTURE", "SKIPPED_BUDGET"}
    with session_factory()() as db:
        assert db.get(BudgetLedger, ledger_id).counters["tools"] == 14


def test_round_deadline_prevents_a_request_after_budget_preparation(simulation):
    _, run_id, _, sources = simulation
    provider = TrackedFixture()
    result = asyncio.run(
        assess_passages(run_id, sources[:1], 2, evaluator=provider, round_seconds=0.000001)
    )
    assert provider.calls == 0 and result["status"] == "UNAVAILABLE"
    assert result["assessments"][0]["reason_code"] == "ASSESSMENT_ROUND_TIMED_OUT"


def test_permission_change_during_call_preserves_cost_but_rejects_result(simulation):
    admin, run_id, ledger_id, sources = simulation

    class RevokingFixture(TrackedFixture):
        async def evaluate(self, projection):
            result = await super().evaluate(projection)
            with Session(admin) as db, db.begin():
                policy = db.scalar(
                    select(PolicyBinding).where(
                        PolicyBinding.resource_type == "SOURCE",
                        PolicyBinding.resource_id == sources[0]["source_id"],
                    )
                )
                policy.egress, policy.version = "DENY", policy.version + 1
            return result

    provider = RevokingFixture()
    with pytest.raises(DomainError, match="PROCESSING_PERMISSION_CHANGED"):
        asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    assert provider.calls == 1
    with session_factory()() as db:
        assert db.get(BudgetLedger, ledger_id).counters["tools"] == 2
        assert not db.scalars(
            select(RetrievalAssessment).where(
                RetrievalAssessment.run_id == run_id,
                RetrievalAssessment.source_id == sources[0]["source_id"],
            )
        ).all()


@pytest.mark.parametrize("counters", [{"tokens": 12000}, {"tools": 20}])
def test_hard_global_budget_blocks_before_transport(simulation, counters):
    admin, run_id, ledger_id, sources = simulation
    with Session(admin) as db, db.begin():
        ledger = db.get(BudgetLedger, ledger_id)
        ledger.counters = {**ledger.counters, **counters}
    provider = TrackedFixture()
    result = asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    assert provider.calls == 0 and result["status"] == "SKIPPED_BUDGET"
    assert result["assessments"][0]["usage_state"] == "NOT_CALLED"
