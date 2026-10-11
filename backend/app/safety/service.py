import re

from app.safety.rules import DANGERS, FORBIDDEN, ISOLATION_ACTIONS, VERSION
from app.safety.schemas import SafetyDecision


def evaluate(
    raw_text: str,
    facts: dict,
    qualifications: tuple[str, ...] = (),
    requested_actions: tuple[str, ...] = (),
    coverage: bool | None = None,
    contradictions: tuple[str, ...] = (),
) -> SafetyDecision:
    confirmed: list[str] = []
    uncertain = []
    structured_dangers = {
        "smoke": "烟雾",
        "burning_smell": "焦味",
        "abnormal_heat": "异常高温",
        "violent_vibration": "剧烈振动",
        "metal_friction": "金属摩擦声",
        "loose_part": "部件松脱",
    }
    confirmed.extend(
        label for field, label in structured_dangers.items() if facts.get(field) is True
    )
    for danger in DANGERS:
        for match in re.finditer(re.escape(danger), raw_text):
            before = raw_text[max(0, match.start() - 15) : match.start()]
            after = raw_text[match.end() : match.end() + 12]
            clause_prefix = re.split(r"[，。；\n]", before)[-1]
            if re.search(r"(?:没有|无|未发现|不存在)\s*$", clause_prefix):
                continue
            if re.search(r"不确定|疑似|可能|似乎|昨天|此前", clause_prefix) or re.search(
                r"不确定|无法判断", after
            ):
                uncertain.append(danger)
            else:
                confirmed.append(danger)
    reasons, rules = [], []
    if confirmed or facts.get("alarm_code") == "A205":
        reasons.extend(confirmed or ["A205 高温报警"])
        rules.extend(["SAFE-01", "A205"] if facts.get("alarm_code") == "A205" else ["SAFE-01"])
    for action in FORBIDDEN:
        if action in raw_text or any(action in step for step in requested_actions):
            reasons.append("禁止操作")
            rules.append("SAFE-03")
    if reasons:
        return SafetyDecision(
            status="STOP_AND_ESCALATE",
            safety_blocked=True,
            escalate_expert=True,
            rule_ids=tuple(dict.fromkeys(rules)),
            instructions=("立即停机并升级专家，禁止继续危险试运行。",),
            forbidden_actions=FORBIDDEN,
            reasons=tuple(reasons),
            rule_version=VERSION,
        )
    if contradictions or coverage is False or uncertain or facts.get("risk_unknown"):
        return SafetyDecision(
            status="CONFLICT_BLOCKED" if contradictions else "RISK_UNKNOWN",
            safety_blocked=True,
            escalate_expert=True,
            rule_ids=("SAFE-05",),
            instructions=("停止进一步操作，由专家核实证据与风险。",),
            forbidden_actions=FORBIDDEN,
            reasons=tuple(contradictions) or tuple(uncertain) or ("无覆盖或风险无法判断",),
            rule_version=VERSION,
        )
    if (
        any("气路拆装" in action or "轴承维修" in action for action in requested_actions)
        and "MECHANICAL" not in qualifications
    ):
        return SafetyDecision(
            status="RISK_UNKNOWN",
            safety_blocked=True,
            escalate_expert=True,
            rule_ids=("SAFE-04",),
            instructions=("交由相应授权机械人员处理，不得自行操作。",),
            forbidden_actions=FORBIDDEN,
            reasons=("缺少适用维修资质",),
            rule_version=VERSION,
        )
    if any("伺服维修" in action for action in requested_actions) and not {
        "MECHANICAL",
        "ELECTRICAL",
    }.intersection(qualifications):
        return SafetyDecision(
            status="RISK_UNKNOWN",
            safety_blocked=True,
            escalate_expert=True,
            rule_ids=("SAFE-04",),
            instructions=("交由相应授权维修人员处理，不得自行操作。",),
            forbidden_actions=FORBIDDEN,
            reasons=("缺少适用维修资质",),
            rule_version=VERSION,
        )
    if (
        any(
            any(term in action for term in ("拆线", "绝缘", "加热回路", "检查线路"))
            for action in requested_actions
        )
        and "ELECTRICAL" not in qualifications
    ):
        return SafetyDecision(
            status="RISK_UNKNOWN",
            safety_blocked=True,
            escalate_expert=True,
            rule_ids=("SAFE-04",),
            instructions=("交由授权电气人员处理，不得自行操作。",),
            forbidden_actions=FORBIDDEN,
            reasons=("缺少适用维修资质",),
            rule_version=VERSION,
        )
    preconditions: tuple[str, ...] = ()
    if any(any(term in action for term in ISOLATION_ACTIONS) for action in requested_actions):
        preconditions = ("操作前断电、锁定挂牌并确认残余能量释放。",)
    return SafetyDecision(
        status="CLEAR",
        safety_blocked=False,
        escalate_expert=False,
        rule_ids=("SAFE-02",) if preconditions else (),
        instructions=preconditions,
        forbidden_actions=FORBIDDEN,
        reasons=(),
        rule_version=VERSION,
    )
