import pytest

from app.diagnosis.normalization import normalize
from app.incidents.schemas import IncidentInput


@pytest.mark.parametrize(
    "text,field",
    [
        ("A203，可能已预热", "preheating_confirmed"),
        ("A203，未确认已预热", "preheating_confirmed"),
        ("A203，还没有预热完成", "preheating_confirmed"),
        ("A203，可能未预热", "preheating_confirmed"),
        ("A203，上次已预热", "preheating_confirmed"),
        ("A203，实际128左右", "actual_temperature_c"),
        ("A203，不是实际128", "actual_temperature_c"),
        ("A203，上次实际128", "actual_temperature_c"),
        ("可能A203", "alarm_code"),
        ("A203，我觉得当前实际128", "actual_temperature_c"),
        ("A203，实际128K", "actual_temperature_c"),
        ("A203，电流0mA", "heating_current_a"),
        ("A310，上游压力580kPa", "upstream_pressure_mpa"),
    ],
)
def test_speculation_negation_or_history_is_not_current_fact(text, field):
    facts, unknowns, _, _ = normalize(IncidentInput(raw_description=text))
    assert field not in facts
    assert unknowns


def test_confirmed_form_can_supply_current_fact_without_erasing_original_unknown():
    facts, unknowns, _, origins = normalize(
        IncidentInput(raw_description="A203，可能已预热", preheating_confirmed=True)
    )
    assert facts["preheating_confirmed"] is True
    assert origins["preheating_confirmed"] == "FORM"
    assert unknowns


def test_text_numeric_overflow_is_explicitly_unknown():
    facts, unknowns, _, _ = normalize(IncidentInput(raw_description="A203，实际" + "9" * 400))
    assert "actual_temperature_c" not in facts
    assert unknowns


def test_known_facts_and_conflicts_keep_provenance():
    facts, _, contradictions, origins = normalize(
        IncidentInput(
            raw_description="A203，设定165，实际128，电流0，已预热",
            readings=[{"metric": "actual_temperature_c", "value": 130, "unit": "C"}],
        )
    )
    assert facts["actual_temperature_c"] == 130
    assert contradictions == ["actual_temperature_c"]
    assert origins["actual_temperature_c"] == "FORM"
    assert origins["heating_current_a"] == "TEXT"


def test_current_measurement_can_follow_historical_comparison_in_same_clause():
    facts, _, _, _ = normalize(IncidentInput(raw_description="A203，上次检查后当前实际128"))
    assert facts["actual_temperature_c"] == 128


def test_uncertain_high_temperature_alarm_remains_blocking_risk():
    facts, unknowns, _, _ = normalize(IncidentInput(raw_description="可能报警A205"))
    assert "alarm_code" not in facts
    assert facts["risk_unknown"] is True
    assert unknowns


def test_unknown_observation_is_not_a_confirmed_fact():
    facts, unknowns, _, origins = normalize(
        IncidentInput(
            raw_description="A101",
            observations={"p1_indicator_state": "UNKNOWN", "panel_state": None},
        )
    )
    assert "p1_indicator_state" not in facts
    assert "p1_indicator_state" not in origins
    assert "panel_state" not in facts
    assert any("p1_indicator_state" in item for item in unknowns)


def test_user_possible_cause_is_not_promoted_into_confirmed_root_or_observation():
    facts, unknowns, _, _ = normalize(
        IncidentInput(
            raw_description="A310，似乎漏气，我觉得可能是接头松了",
            observations={"continuous_leak_sound": None},
        )
    )
    assert facts == {"alarm_code": "A310"}
    assert unknowns


def test_conflicting_text_and_form_preserve_conflict_instead_of_silently_resolving():
    facts, _, conflicts, origins = normalize(
        IncidentInput(
            raw_description="A203，A310，实际128，实际130，已预热，未预热",
            alarm_code="A203",
            preheating_confirmed=True,
            readings=[{"metric": "actual_temperature_c", "value": 132, "unit": "C"}],
        )
    )
    assert set(conflicts) == {"alarm_code", "actual_temperature_c", "preheating_confirmed"}
    assert facts["actual_temperature_c"] == 132
    assert origins["actual_temperature_c"] == "FORM"


def test_known_negative_observation_is_distinct_from_unknown():
    facts, unknowns, _, origins = normalize(
        IncidentInput(raw_description="A310", observations={"continuous_leak_sound": False})
    )
    assert facts["continuous_leak_sound"] is False
    assert origins["continuous_leak_sound"] == "FORM"
    assert unknowns == []
