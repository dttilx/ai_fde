import copy

import pytest
from pydantic import ValidationError

from app.incidents.schemas import IncidentInput, Reading
from app.knowledge.templates import a203_support

FACTS = {
    "alarm_code": "A203",
    "set_temperature_c": 165,
    "actual_temperature_c": 128,
    "heating_current_a": 0,
    "preheating_confirmed": True,
}
SOURCES = {"A203", "H02", "WO-240-042", "SAFE-01", "SAFE-02", "SAFE-04", "SAFE-05"}


def test_reference_fixture_is_eligible_but_not_a_confirmed_root_cause():
    proof = a203_support(FACTS, ("ELECTRICAL",), SOURCES)
    assert proof.valid and "FIXTURE" in proof.template_id
    assert not proof.failed_predicates


@pytest.mark.parametrize(
    "field,value",
    [
        ("alarm_code", "A310"),
        ("actual_temperature_c", 165),
        ("heating_current_a", 3),
        ("preheating_confirmed", False),
        ("actual_temperature_c", None),
        ("actual_temperature_c", "128"),
        ("heating_current_a", False),
        ("preheating_confirmed", 1),
        ("actual_temperature_c", float("nan")),
    ],
)
def test_changed_unknown_or_wrong_type_fact_cannot_auto_validate(field, value):
    facts = {**FACTS, field: value}
    proof = a203_support(facts, ("ELECTRICAL",), SOURCES)
    assert not proof.valid
    assert field in proof.failed_predicates


@pytest.mark.parametrize("missing", sorted(FACTS))
def test_required_fact_cannot_be_filled_by_reference_fixture(missing):
    facts = copy.deepcopy(FACTS)
    del facts[missing]
    assert not a203_support(facts, ("ELECTRICAL",), SOURCES).valid
    assert missing not in facts  # checker must not write an expected reading into input.


@pytest.mark.parametrize("missing", sorted(SOURCES))
def test_missing_source_is_not_replaced_by_a_canned_proof(missing):
    proof = a203_support(FACTS, ("ELECTRICAL",), SOURCES - {missing})
    assert not proof.valid and "REQUIRED_SOURCES" in proof.failed_predicates


def test_role_or_conflicting_evidence_does_not_waive_checks():
    assert not a203_support(FACTS, ("EXPERT",), SOURCES).valid
    assert not a203_support(FACTS, ("ELECTRICAL",), SOURCES, ("temperature_conflict",)).valid


@pytest.mark.parametrize("value", [False, True, "0"])
def test_numeric_form_does_not_coerce_boolean_or_text_into_current(value):
    with pytest.raises(ValidationError):
        Reading(metric="heating_current_a", value=value, unit="A")


@pytest.mark.parametrize("value", [1, "true"])
def test_preheat_requires_an_explicit_boolean(value):
    with pytest.raises(ValidationError):
        IncidentInput(raw_description="A203", preheating_confirmed=value)
