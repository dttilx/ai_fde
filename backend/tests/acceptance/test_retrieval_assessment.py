"""Independent fixture boundary acceptance; no real Jev accuracy is claimed."""

import asyncio
import json

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import select

from app.knowledge.models import SourceRecord
from app.knowledge.passage_assessment import assess_passages, context_complete, route
from app.shared.config import PROJECT_ROOT
from app.shared.db import session_factory
from app.shared.providers.jev import JevEvaluation, JevJudgment
from app.shared.providers.jev_payload import build_projection, project_confirmed_facts
from app.shared.providers.protocols import ProviderFailure
from tests.integration.test_jev_stage import TrackedFixture

pytest_plugins = ["tests.integration.test_jev_stage"]


@pytest.mark.parametrize(
    "alarm,observations",
    [
        ("A101", {"material_present": False, "p1_indicator_state": "OFF"}),
        ("A401", {"door_closed": True, "door_alarm_persists_after_reclose": True}),
        ("A520", {"visible_jam": False}),
        (
            "A900",
            {
                "affected_modules": ["CONTROLLER", "P1"],
                "panel_state": "ALARM",
                "onset_phase": "STARTUP",
            },
        ),
    ],
)
def test_manual_alarm_domain_projection_and_missing_context(alarm, observations):
    facts = {"alarm_code": alarm, **observations}
    projected = project_confirmed_facts(facts)
    assert context_complete(facts)
    for key, value in observations.items():
        assert projected["device_states"][key] == value
    request, _ = build_projection(
        "jev-fixture-v1",
        projected,
        [
            {
                "source_id": "local-private-id",
                "kind": "MANUAL",
                "approved_excerpt": "Self-authored fixture only.",
            }
        ],
        ("relevance", "applicability", "instruction_signal"),
    )
    assert {value["type"] for value in request["questions"].values()} == {"score", "choice", "noul"}
    assert "local-private-id" not in json.dumps(request)
    missing = {"alarm_code": alarm}
    assert not context_complete(missing)
    assert route(JevJudgment(), {"pinned": False, "collection": "MANUAL"}, False) == "UNASSESSED"


def test_alarm_mapping_matches_retained_manual_not_guessed_names():
    alarms = json.loads(
        (PROJECT_ROOT / "knowledge/seed/alarm-codes.json").read_text(encoding="utf-8")
    )
    by_key = {row["id"]: row["excerpt"] for row in alarms}
    assert "安全门未闭合" in by_key["A401"] and "伺服过载" in by_key["A520"]
    assert not context_complete({"alarm_code": "A401", "visible_jam": True})
    assert not context_complete({"alarm_code": "A520", "door_closed": True})


def test_uncertain_module_or_broad_legacy_panel_never_becomes_a_specific_state():
    assert not context_complete(
        {
            "alarm_code": "A900",
            "affected_modules": ["UNKNOWN"],
            "panel_state": "NORMAL",
            "onset_phase": "STARTUP",
        }
    )
    projected = project_confirmed_facts({"panel_state": "ABNORMAL", "onset_phase": "RUNNING"})
    assert projected["device_states"]["panel_state"] == "UNKNOWN"
    assert projected["device_states"]["onset_phase"] == "UNKNOWN"


def test_exam_input_is_denied_before_fixture_transport(simulation):
    _, run_id, _, _ = simulation
    with session_factory()() as db:
        source = db.scalar(select(SourceRecord).where(SourceRecord.source_key == "SAFE-01"))
        candidate = {
            "source_id": source.id,
            "source_key": source.source_key,
            "release_id": source.release_id,
            "collection": source.collection,
            "pinned": True,
            "checksum": source.checksum,
        }
    provider = TrackedFixture()
    result = asyncio.run(assess_passages(run_id, [candidate], 2, evaluator=provider))
    assert provider.calls == 0 and result["status"] == "SKIPPED_POLICY"
    assert result["assessments"][0]["route"] == "REQUIRED"
    schema = json.loads(
        (
            PROJECT_ROOT
            / "specs/001-apx240-multimodal-diagnosis/contracts/retrieval-assessment.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors(result)) == []


def test_transient_retry_has_aggregate_unknown_usage_and_no_more_than_two_calls(simulation):
    _, run_id, _, sources = simulation

    class RetryFixture(TrackedFixture):
        async def evaluate(self, projection):
            if self.calls == 0:
                self.calls += 1
                raise ProviderFailure("TEMPORARY_UNAVAILABLE")
            return await super().evaluate(projection)

    provider = RetryFixture()
    result = asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=provider))
    assert provider.calls == 2 and result["status"] == "FIXTURE"
    assert result["assessments"][0]["usage_state"] == "UNKNOWN"


def test_invalid_judgment_and_provider_error_text_do_not_become_success_or_leak(simulation):
    _, run_id, _, sources = simulation

    class MalformedFixture(TrackedFixture):
        async def evaluate(self, projection):
            self.calls += 1
            return JevEvaluation({"category": "CONFIRMED_ROOT_CAUSE"}, self.model, "FIXTURE", 0)

    result = asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=MalformedFixture()))
    assert result["status"] == "UNAVAILABLE" and result["assessments"][0]["relevance_level"] is None

    class ErrorFixture(TrackedFixture):
        model = "safe-fixture-error-v1"

        async def evaluate(self, projection):
            raise ProviderFailure("secret-customer-private-response")

    result = asyncio.run(assess_passages(run_id, sources[:1], 2, evaluator=ErrorFixture()))
    assert "secret-customer" not in json.dumps(result)
    assert result["assessments"][0]["reason_code"] == "PROVIDER_FAILURE"
