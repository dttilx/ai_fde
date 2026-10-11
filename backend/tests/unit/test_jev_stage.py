from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.knowledge.passage_assessment import context_complete, route, summary_status
from app.shared.providers.jev import JevJudgment
from app.shared.providers.jev_payload import UNKNOWN_STATES, project_confirmed_facts


def distribution(category):
    return {
        key: float(key == category)
        for key in (
            "TECHNICAL_EVIDENCE",
            "HISTORICAL_REFERENCE",
            "BACKGROUND",
            "UNRELATED",
            "CONFLICT_REVIEW",
            "UNKNOWN",
        )
    }


def test_score_choice_and_instruction_signal_cannot_remove_required_sources():
    judgment = JevJudgment(
        relevance_level=0,
        category="UNRELATED",
        confidence=0.99,
        probabilities=distribution("UNRELATED"),
        instruction_signal="FALSE",
    )
    assert route(judgment, {"pinned": True, "collection": "SAFETY_RULE"}, True) == "REQUIRED"
    assert (
        route(judgment, {"pinned": False, "collection": "HISTORICAL_CASE"}, True)
        == "HISTORICAL_REFERENCE"
    )
    assert route(judgment, {"pinned": False, "collection": "MANUAL"}, True) == "FOLDED"
    assert route(judgment, {"pinned": False, "collection": "MANUAL"}, False) == "UNASSESSED"
    judgment.instruction_signal = "TRUE"
    assert route(judgment, {"pinned": True, "collection": "SAFETY_RULE"}, True) == "CONFLICT_REVIEW"


@pytest.mark.parametrize(
    "change",
    [
        {"confidence": 0.79},
        {"instruction_signal": "UNKNOWN"},
        {"relevance_level": 1},
        {"probabilities": None},
    ],
)
def test_unrelated_folding_requires_all_thresholds_and_no_uncertain_signal(change):
    data = {
        "relevance_level": 0,
        "category": "UNRELATED",
        "confidence": 0.99,
        "probabilities": distribution("UNRELATED"),
        "instruction_signal": "FALSE",
        **change,
    }
    assert (
        route(JevJudgment(**data), {"pinned": False, "collection": "MANUAL"}, True) == "UNASSESSED"
    )


@pytest.mark.parametrize(
    "data",
    [
        {"relevance_level": True},
        {"relevance_level": 4},
        {"confidence": float("nan")},
        {"confidence": -0.01},
        {"category": "CONFIRMED_ROOT_CAUSE"},
        {"probabilities": {"UNRELATED": 1.0}},
        {"instruction_signal": True},
    ],
)
def test_invalid_provider_judgment_never_becomes_support(data):
    with pytest.raises(ValidationError):
        JevJudgment(**data)


def test_minimal_projection_retains_unknown_and_false_without_identifiers():
    facts = {
        "alarm_code": "A101",
        "material_present": False,
        "p1_indicator_state": "UNKNOWN",
        "asset_id": "secret-asset",
        "observation_time": "secret-time",
        "root_cause": "guess",
    }
    projected = project_confirmed_facts(facts)
    assert projected["device_states"]["material_present"] is False
    assert projected["device_states"]["p1_indicator_state"] == "UNKNOWN"
    assert projected["device_states"]["door_closed"] is None
    assert "secret" not in str(projected)
    assert not context_complete(facts)
    facts["p1_indicator_state"] = "OFF"
    assert context_complete(facts)
    assert project_confirmed_facts({})["device_states"] == deepcopy(UNKNOWN_STATES)


def test_status_is_derived_from_actual_rows_and_no_results_are_explicit():
    assert summary_status([]) == "NO_CANDIDATES"
    assert summary_status([{"status": "CACHED"}]) == "CACHED"
    assert summary_status([{"status": "FIXTURE"}, {"status": "SKIPPED_POLICY"}]) == "PARTIAL"
