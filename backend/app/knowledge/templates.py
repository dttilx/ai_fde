from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateSupport:
    valid: bool
    template_id: str
    failed_predicates: tuple[str, ...]


def a310_support(facts, qualifications, source_keys, contradictions=()) -> TemplateSupport:
    expected = {
        "alarm_code": "A310",
        "upstream_pressure_mpa": 0.64,
        "device_pressure_mpa": 0.41,
        "continuous_leak_sound": True,
    }
    failed = [
        key
        for key, value in expected.items()
        if key not in facts
        or facts[key] != value
        or (
            type(facts[key]) is not bool
            if type(value) is bool
            else type(facts[key]) not in {float, int}
            if type(value) in {float, int}
            else type(facts[key]) is not str
        )
    ]
    if "MECHANICAL" not in qualifications:
        failed.append("MECHANICAL_QUALIFICATION")
    if not {
        "A310",
        "H03",
        "WO-240-051",
        "MANUAL-P2",
        *[f"SAFE-0{i}" for i in range(1, 6)],
    }.issubset(source_keys):
        failed.append("REQUIRED_SOURCES")
    if contradictions:
        failed.append("CONTRADICTIONS")
    return TemplateSupport(not failed, "A310-REFERENCE-FIXTURE-v1", tuple(failed))


def a203_support(
    facts: dict,
    qualifications: tuple[str, ...],
    source_keys: set[str],
    contradictions: tuple[str, ...] = (),
) -> TemplateSupport:
    """Narrow approved feature-reference fixture predicate, never generalized model approval."""
    expected = {
        "alarm_code": "A203",
        "set_temperature_c": 165,
        "actual_temperature_c": 128,
        "heating_current_a": 0,
        "preheating_confirmed": True,
    }
    failed = []
    for field, value in expected.items():
        observed = facts.get(field)
        valid_type = (
            type(observed) is bool
            if type(value) is bool
            else type(observed) in {int, float}
            if type(value) in {int, float}
            else type(observed) is str
        )
        if field not in facts or not valid_type or observed != value:
            failed.append(field)
    if "ELECTRICAL" not in qualifications:
        failed.append("ELECTRICAL_QUALIFICATION")
    if not {"A203", "H02", "WO-240-042", "SAFE-01", "SAFE-02", "SAFE-04", "SAFE-05"}.issubset(
        source_keys
    ):
        failed.append("REQUIRED_SOURCES")
    if contradictions:
        failed.append("CONTRADICTIONS")
    return TemplateSupport(not failed, "A203-REFERENCE-FIXTURE-v1", tuple(failed))
