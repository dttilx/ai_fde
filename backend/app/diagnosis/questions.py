"""Source-bound required facts; unanswered observations stay unknown."""

from sqlalchemy import select

from app.diagnosis.models import PendingHumanAction
from app.shared.errors import DomainError

REQUIRED = {
    "A203": [
        "set_temperature_c",
        "preheating_confirmed",
        "actual_temperature_c",
        "heating_current_a",
    ],
    "A310": ["upstream_pressure_mpa", "device_pressure_mpa", "continuous_leak_sound"],
}
BOOLEAN_FIELDS = {"preheating_confirmed", "continuous_leak_sound"}
RISK_FIELDS = {
    "smoke",
    "burning_smell",
    "abnormal_heat",
    "violent_vibration",
    "metal_friction",
    "loose_part",
}
LABELS = {
    "set_temperature_c": "设定温度（°C）",
    "preheating_confirmed": "是否已预热",
    "actual_temperature_c": "实际温度（°C）",
    "heating_current_a": "加热电流（A）",
    "upstream_pressure_mpa": "上游压力（MPa）",
    "device_pressure_mpa": "设备端压力（MPa）",
    "continuous_leak_sound": "是否有持续漏气声",
}


def missing_fields(facts):
    return [key for key in REQUIRED.get(facts.get("alarm_code"), []) if key not in facts]


def question_details(facts, citations):
    alarm = facts.get("alarm_code")
    source = next((c for c in citations if c["source_ref"] == alarm), None)
    if not source:
        raise DomainError("QUESTION_SOURCE_MISSING", 409)
    return [
        {
            "field": key,
            "text": LABELS[key],
            "blocking": True,
            "reason": "按报警码排查顺序补齐当前事实；历史案例读数不能代替现场输入。",
            "citation_ids": [source["citation_id"]],
            "source_ref": alarm,
            "locator": source["locator"],
        }
        for key in missing_fields(facts)
    ]


def persist_questions(db, run, snapshot, details):
    existing = db.scalar(
        select(PendingHumanAction).where(
            PendingHumanAction.run_id == run.id,
            PendingHumanAction.snapshot_hash == snapshot.content_hash,
            PendingHumanAction.kind == "INFORMATION",
        )
    )
    if existing is None:
        db.add(
            PendingHumanAction(
                run_id=run.id,
                snapshot_hash=snapshot.content_hash,
                kind="INFORMATION",
                reasons=details,
                assigned_actor_id=run.actor_id,
            )
        )
