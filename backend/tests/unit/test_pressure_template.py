import pytest

from app.knowledge.template_registry import required_source_keys
from app.knowledge.templates import a310_support

FACTS = {
    "alarm_code": "A310",
    "upstream_pressure_mpa": 0.64,
    "device_pressure_mpa": 0.41,
    "continuous_leak_sound": True,
}


def test_pressure_reference_requires_current_facts_qualification_and_sources():
    assert a310_support(FACTS, ("MECHANICAL",), required_source_keys("A310")).valid
    assert not a310_support(FACTS, ("ELECTRICAL",), required_source_keys("A310")).valid
    assert not a310_support(FACTS, ("MECHANICAL",), {"A310", "H03"}).valid
    assert not a310_support(
        FACTS, ("MECHANICAL",), required_source_keys("A310"), ("pressure",)
    ).valid


@pytest.mark.parametrize(
    "field,value",
    [
        ("upstream_pressure_mpa", None),
        ("device_pressure_mpa", 0.62),
        ("continuous_leak_sound", False),
        ("continuous_leak_sound", 1),
        ("continuous_leak_sound", "true"),
        ("upstream_pressure_mpa", "0.64"),
    ],
)
def test_missing_different_or_wrong_type_facts_never_get_template_approval(field, value):
    changed = {**FACTS, field: value}
    assert not a310_support(changed, ("MECHANICAL",), required_source_keys("A310")).valid


def test_safety_api_exposes_only_advisory_actions():
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/safety/rules" in paths
    assert not any(
        any(term in path.lower() for term in ("/plc", "/equipment-control", "/set-parameter"))
        for path in paths
    )
