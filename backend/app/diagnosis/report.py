import json

from jsonschema import Draft202012Validator

from app.shared.config import PROJECT_ROOT
from app.shared.errors import DomainError
from app.shared.versioning import content_hash

LABELS = {
    "alarm_code": "报警码",
    "set_temperature_c": "设定温度",
    "actual_temperature_c": "实际温度",
    "heating_current_a": "加热电流",
    "preheating_confirmed": "已预热",
    "upstream_pressure_mpa": "上游压力",
    "device_pressure_mpa": "设备端压力",
    "continuous_leak_sound": "持续漏气声",
    "observation_time": "观察时间",
}
UNITS = {
    "set_temperature_c": "°C",
    "actual_temperature_c": "°C",
    "heating_current_a": "A",
    "upstream_pressure_mpa": "MPa",
    "device_pressure_mpa": "MPa",
}


def validate_report(report: dict) -> None:
    schema = json.loads(
        (
            PROJECT_ROOT
            / "specs/001-apx240-multimodal-diagnosis/contracts/diagnosis-report.schema.json"
        ).read_text(encoding="utf-8")
    )
    if list(Draft202012Validator(schema).iter_errors(report)):
        raise DomainError("REPORT_CONTRACT_INVALID", 500)
    references = {citation["citation_id"] for citation in report["evidence_sources"]}
    for area in (
        "possible_causes",
        "manual_references",
        "safety_preconditions",
        "check_sequence",
        "stop_conditions",
        "escalation_reasons",
        "immediate_safety_actions",
    ):
        for item in report[area]:
            if not item["citation_ids"] or not set(item["citation_ids"]).issubset(references):
                raise DomainError("REPORT_CITATION_INVALID", 500)


def a203_draft(
    run_id: str,
    version_id: str,
    facts: dict,
    evidence: list[dict],
    citations: list[dict],
    unknowns: list[str],
    qualification_refs: list[dict],
    mode: str,
    decision_id: str,
    check_ids: list[str],
    reviewer_ids: list[str] | None = None,
) -> dict:
    by_key = {citation["source_ref"]: citation["citation_id"] for citation in citations}

    def cite(*keys):
        return [by_key[key] for key in keys if key in by_key]

    evidence_ids = [row["id"] for row in evidence]

    def instruction(index, text, sources, qualification=False, step=None):
        return {
            "instruction_id": f"{version_id}:instruction:{index}:{content_hash(text)[:8]}",
            "order": index,
            "text": text,
            "citation_ids": cite(*sources),
            "evidence_ids": evidence_ids if step else [],
            "alarm_step_ref": step,
            "required_qualification": ["ELECTRICAL"] if qualification else [],
            "execution_boundary": "AUTHORIZED_PERSONNEL_REQUIRED"
            if qualification
            else "OBSERVATION_ONLY",
            "policy_reference_ids": [ref["policy_reference_id"] for ref in qualification_refs]
            if qualification
            else [],
        }

    known = [
        {
            "text": (
                f"{LABELS.get(row['key'], row['key'])}："
                f"{format_fact(row['value'])} "
                f"{UNITS.get(row['key'], '')}"
            ).strip(),
            "evidence_version_ids": [row["id"]],
            "status": row["state"],
        }
        for row in evidence
        if not row.get("media_id")
    ]
    causes = []
    for rank, (cause, refs, reason) in enumerate(
        [
            (
                "H1 加热回路开路",
                ("A203", "H02", "WO-240-042"),
                "当前读数与 H02 的相似性须逐项核对；仍须授权电气检查确认。",
            ),
            ("继电器或线路故障", ("A203",), "报警码列出的替代原因；当前尚无回路检查证据。"),
            ("T1 温度传感器偏差", ("A203",), "报警码列出的替代原因；缺少独立温度对照，证据较弱。"),
        ],
        1,
    ):
        causes.append(
            {
                "claim_id": f"{version_id}:cause:{rank}",
                "rank": rank,
                "cause": cause,
                "status": "POSSIBLE",
                "citation_ids": cite(*refs),
                "supporting_evidence_ids": evidence_ids,
                "counter_evidence_ids": [],
                "missing_evidence": ["授权检查结果尚未提供"],
                "ranking_reason": reason,
            }
        )
    optional = [
        {
            "question_id": "recent-maintenance",
            "text": "如有近期维修或换产记录，可补充供后续对照。",
            "reason": "非阻断背景信息，不影响本次有证据的可能原因报告。",
            "citation_ids": cite("WO-240-042"),
            "related_evidence_ids": [],
            "blocking": False,
        }
    ]
    report = {
        "report_version_id": version_id,
        "diagnosis_run_id": run_id,
        "status": "COMPLETED" if mode != "PENDING_REVIEW" else "FINALIZING",
        "publication_status": "PUBLISHED" if mode != "PENDING_REVIEW" else "DRAFT",
        "fault_phenomenon": "A203 热封温度低；当前读数与预热信息见已知事实。",
        "safety_blocked": False,
        "known_facts": known,
        "confirmed_observations": [
            {
                "text": f"已复核{row['source']}候选：{LABELS.get(row['key'], row['key'])}"
                f"={format_fact(row['value'])}{UNITS.get(row['key'], '')}；"
                f"定位 {row.get('locators', {})}",
                "evidence_version_ids": [row["id"]],
                "status": row["state"],
            }
            for row in evidence
            if row.get("media_id")
        ],
        "unconfirmed_information": [
            {"text": item, "source_refs": [], "reason": "用户推测或尚未完成现场验证"}
            for item in unknowns
        ]
        + [{"text": "最终根因未确认", "source_refs": [], "reason": "AI 只能提出可能原因"}],
        "contradictions": [],
        "manual_references": [
            {"text": "说明书热封设定温度为165°C。", "citation_ids": cite("MANUAL-P2")}
        ],
        "possible_causes": causes,
        "historical_comparisons": [
            {
                "citation_ids": cite("H02", "WO-240-042"),
                "current_evidence_ids": evidence_ids,
                "same_points": ["均为 A203。"]
                + [
                    f"{LABELS[key]}与 H02 相同：{expected}{UNITS[key]}。"
                    for key, expected in {
                        "set_temperature_c": 165,
                        "actual_temperature_c": 128,
                        "heating_current_a": 0,
                    }.items()
                    if facts.get(key) == expected
                ],
                "different_points": ["历史工单已完成维修与复机验证；本次尚未完成检查。"]
                + [
                    f"{LABELS[key]}与 H02 不同：本次{facts.get(key)}，历史{expected}{UNITS[key]}。"
                    for key, expected in {
                        "set_temperature_c": 165,
                        "actual_temperature_c": 128,
                        "heating_current_a": 0,
                    }.items()
                    if facts.get(key) != expected
                ],
                "missing_information": ["当前回路检查、维修与复机结果"],
                "effect_on_diagnosis": "历史记录支持可能原因，不能替代本次根因确认。",
            }
        ],
        "evidence_sources": citations,
        "policy_references": qualification_refs,
        "immediate_safety_actions": [],
        "safety_preconditions": [
            instruction(
                1, "涉及线路或加热组件前，必须断电、锁定挂牌并确认残余能量释放。", ("SAFE-02",)
            ),
            instruction(2, "线路和加热回路检查由相应授权电气人员执行。", ("SAFE-04",), True),
        ],
        "check_sequence": [
            instruction(
                1,
                "核对热封设定与预热记录；本次输入已提供，保留现场记录。",
                ("A203",),
                step="A203:STEP1",
            ),
            instruction(
                2,
                "核对现场实际温度和已有加热电流读数，不据此直接确认根因。",
                ("A203",),
                step="A203:STEP2",
            ),
            instruction(
                3,
                "进一步回路检查前停机、断电、锁定挂牌并释放残余能量。",
                ("A203", "SAFE-02"),
                step="A203:STEP3",
            ),
            instruction(
                4,
                "由授权电气人员检查加热回路、继电器、线路和温度检测链路。",
                ("A203", "SAFE-04"),
                True,
                "A203:STEP4",
            ),
        ],
        "missing_information": optional,
        "stop_conditions": [
            instruction(
                1,
                "出现烟雾、焦味、异常高温、剧烈振动、金属摩擦声或部件松脱时，立即停机并升级专家。",
                ("SAFE-01",),
            ),
            instruction(
                2, "证据矛盾、知识无覆盖或风险不明时停止进一步操作并升级专家。", ("SAFE-05",)
            ),
        ],
        "escalation_reasons": [],
        "escalate_expert": False,
        "evidence_sufficiency": "SUFFICIENT_FOR_POSSIBILITIES",
        "limitations": [
            "FIXTURE/RULE 演示：未调用真实生成模型或外部 Jev，不代表模型诊断质量。",
            "模板治理批准为明确标记的 fixture 模拟，不代表生产人工审定。",
            "部分手册字形未识别；未使用不完整范围参数作判断。",
            "未执行设备操作；未确认根因或批准复机。",
        ],
        "claim_review_ids": [],
        "reviewer_ids": reviewer_ids or [],
        "release_mode": mode,
        "release_policy_version": "apx-release-v2.2",
        "release_decision_id": decision_id,
        "validation_check_ids": check_ids,
    }
    validate_report(report)
    return report


def format_fact(value) -> str:
    return ("是" if value else "否") if type(value) is bool else str(value)
