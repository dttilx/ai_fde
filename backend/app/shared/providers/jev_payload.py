import json
import re
import secrets
from typing import Any

from jsonschema import Draft202012Validator

from app.shared.config import PROJECT_ROOT
from app.shared.errors import DomainError

SCHEMA_PATH = (
    PROJECT_ROOT / "specs/001-apx240-multimodal-diagnosis/contracts/jev-payload.schema.json"
)
UNKNOWN_STATES: dict[str, Any] = {
    "material_present": None,
    "p1_indicator_state": "UNKNOWN",
    "door_closed": None,
    "door_alarm_persists_after_reclose": None,
    "visible_jam": None,
    "affected_modules": [],
    "panel_state": "UNKNOWN",
    "onset_phase": "UNKNOWN",
}


def project_confirmed_facts(facts: dict) -> dict:
    """Only typed confirmed domain facts; no raw text, identities, times or asset IDs."""
    from app.diagnosis.normalization import UNITS

    readings = [
        {"metric": key, "value": facts[key], "unit": unit}
        for key, unit in UNITS.items()
        if key in facts and type(facts[key]) in (int, float)
    ]
    phenomena = []
    for key, label in {
        "smoke": "SMOKE",
        "burning_smell": "BURNING_SMELL",
        "abnormal_heat": "ABNORMAL_HEAT",
        "violent_vibration": "VIOLENT_VIBRATION",
        "metal_friction": "METAL_FRICTION",
        "loose_part": "LOOSE_PART",
        "continuous_leak_sound": "CONTINUOUS_LEAK_SOUND",
    }.items():
        if facts.get(key) is True:
            phenomena.append(label)
    state_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["properties"]["state"][
        "properties"
    ]["facts"]["properties"]["device_states"]["properties"]
    states = {}
    for key, default in UNKNOWN_STATES.items():
        value = facts.get(key, default)
        spec = state_schema[key]
        if "enum" in spec and value not in spec["enum"]:
            # A broad legacy observation such as ABNORMAL does not prove ALARM.
            value = default
        states[key] = value
    return {
        "alarm_code": facts.get("alarm_code"),
        "readings": readings,
        "phenomena": phenomena,
        "preheating_confirmed": facts.get("preheating_confirmed"),
        "device_states": states,
    }


SENSITIVE = re.compile(
    r"https?://|(?:[A-Za-z]:\\)|(?:/Users/)|(?:/home/)|(?:WO-\d+-\d+)"
    r"|(?:apx240://)|(?:sk-[A-Za-z0-9]{10,})|(?:\b[\w.+-]+@[\w.-]+\.\w+\b)"
    r"|(?:\b\d{11}\b)|(?:serial[_ -]?number)|(?:customer[_ -]?name)",
    re.I,
)


def validate_projection(payload: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if list(Draft202012Validator(schema).iter_errors(payload)):
        raise DomainError("JEV_PROJECTION_INVALID")
    content = json.dumps(payload["state"], ensure_ascii=False)
    if SENSITIVE.search(content):
        raise DomainError("RESIDUAL_SENSITIVE")


def build_projection(
    model: str,
    facts: dict,
    approved_sources: list[dict],
    question_names: tuple[str, ...],
    claim: str | None = None,
) -> tuple[dict, dict]:
    """Caller must already have authorized every fact/source and approved each excerpt version."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    source_map = {}
    sources = []
    for index, source in enumerate(approved_sources):
        alias = f"P{index + 1}"
        source_map[alias] = {"source_id": source["source_id"], "nonce": secrets.token_hex(8)}
        sources.append(
            {"alias": alias, "kind": source["kind"], "excerpt": source["approved_excerpt"]}
        )
    state = {
        "projection_version": "JEV_MINIMAL_V2",
        "device_family": "PACKAGING",
        "facts": facts,
        "sources": sources,
    }
    if claim is not None:
        state["claim"] = claim
    questions = {}
    for name in question_names:
        spec = schema["properties"]["questions"]["properties"].get(name)
        if spec is None:
            raise DomainError("JEV_QUESTION_INVALID")
        questions[name] = spec["const"]
    payload = {"model": model, "state": state, "questions": questions}
    validate_projection(payload)
    return payload, source_map
