import math
import re

from app.shared.errors import DomainError

UNITS = {
    "set_temperature_c": "C",
    "actual_temperature_c": "C",
    "heating_current_a": "A",
    "upstream_pressure_mpa": "MPa",
    "device_pressure_mpa": "MPa",
}
PATTERNS = {
    "set_temperature_c": r"设定(?:温度)?\s*(\d+(?:\.\d+)?)",
    "actual_temperature_c": r"实际(?:温度)?\s*(\d+(?:\.\d+)?)",
    "heating_current_a": r"(?:加热)?电流\s*(\d+(?:\.\d+)?)",
    "upstream_pressure_mpa": r"上游(?:压力)?\s*(\d+(?:\.\d+)?)",
    "device_pressure_mpa": r"设备端(?:压力)?\s*(\d+(?:\.\d+)?)",
}


def unconfirmed_context(text: str, start: int, end: int) -> bool:
    prefix = re.split(r"[，。；,;\n]", text[:start])[-1]
    current_prefix = re.split(r"本次|当前|现在", prefix)[-1]
    suffix = re.split(r"[，。；,;\n]", text[end:])[0][:8]
    return bool(
        re.search(r"猜测|可能|我觉得|大概|怀疑|不确定|未确认|没有|不是", prefix)
        or re.search(r"上次|历史|昨天|之前", current_prefix)
        or re.search(r"左右|大概|未确认|不确定|[？?]", suffix)
    )


def normalize(body) -> tuple[dict, list, list, dict]:
    facts: dict = {}
    origins, unknowns, conflicts = {}, [], []
    text = body.raw_description
    for field, pattern in PATTERNS.items():
        values = []
        for match in re.finditer(pattern, text):
            suffix = text[match.end() : match.end() + 6]
            if unconfirmed_context(text, match.start(), match.end()):
                unknowns.append(f"{field} 含推测、否定或历史描述，当前读数未确认")
            elif (
                unit := re.match(r"\s*(?:°\s*)?([A-Za-z]+|℃|℉|华氏|开尔文|千帕|毫安)", suffix)
            ) and unit.group(1) not in {UNITS[field], "℃" if UNITS[field] == "C" else UNITS[field]}:
                unknowns.append(f"{field} 原始单位与 {UNITS[field]} 不一致，不能直接使用该读数")
            else:
                number = float(match.group(1))
                if math.isfinite(number):
                    values.append(number)
                else:
                    unknowns.append(f"{field} 数值超出可解析范围，当前读数未确认")
        if values:
            if len(set(values)) > 1:
                conflicts.append(field)
            facts[field] = values[-1]
            origins[field] = "TEXT"
    codes = set()
    for match in re.finditer(r"(?<![A-Za-z0-9])A\d{3}(?![A-Za-z0-9])", text):
        if unconfirmed_context(text, match.start(), match.end()):
            unknowns.append("alarm_code 当前报警码未确认")
            if match.group(0) == "A205":
                facts["risk_unknown"], origins["risk_unknown"] = True, "TEXT"
        else:
            codes.add(match.group(0))
    if len(codes) > 1:
        conflicts.append("alarm_code")
    elif codes:
        facts["alarm_code"] = next(iter(codes))
        origins["alarm_code"] = "TEXT"
    preheat = []
    for match in re.finditer(r"未预热|已预热|预热完成", text):
        if unconfirmed_context(text, match.start(), match.end()):
            unknowns.append("preheating_confirmed 当前预热状态未确认")
        else:
            preheat.append(match.group(0) != "未预热")
    if preheat:
        if len(set(preheat)) > 1:
            conflicts.append("preheating_confirmed")
        facts["preheating_confirmed"] = preheat[-1]
        origins["preheating_confirmed"] = "TEXT"
    form = {}
    if body.observation_time is not None:
        form["observation_time"] = body.observation_time
    if body.alarm_code is not None:
        form["alarm_code"] = body.alarm_code
    if body.preheating_confirmed is not None:
        form["preheating_confirmed"] = body.preheating_confirmed
    for reading in body.readings:
        if reading.unit != UNITS[reading.metric]:
            raise DomainError("READING_UNIT_MISMATCH")
        if reading.metric in form and form[reading.metric] != reading.value:
            conflicts.append(reading.metric)
        form[reading.metric] = reading.value
    allowed = {
        "smoke",
        "burning_smell",
        "abnormal_heat",
        "violent_vibration",
        "metal_friction",
        "loose_part",
        "continuous_leak_sound",
        "material_present",
        "p1_indicator_state",
        "door_closed",
        "door_alarm_persists_after_reclose",
        "visible_jam",
        "panel_state",
        "onset_phase",
    }
    if set(body.observations) - allowed:
        raise DomainError("OBSERVATION_FIELD_INVALID")
    for key, value in body.observations.items():
        if value == "UNKNOWN":
            unknowns.append(f"{key} 现场观察未确认")
        elif value is not None:
            form[key] = value
    for field, value in form.items():
        if field in facts and facts[field] != value:
            conflicts.append(field)
        facts[field] = value
        origins[field] = "FORM"
    if any(term in text for term in ("可能", "似乎", "我觉得", "猜测")):
        unknowns.append("报障中的推测不是确定事实；未确认根因。")
    return facts, unknowns, sorted(set(conflicts)), origins
