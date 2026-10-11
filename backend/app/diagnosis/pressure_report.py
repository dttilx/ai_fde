"""A310 advisory: current pressure facts stay separate from historical repair results."""

from app.diagnosis.report import LABELS, UNITS, format_fact, validate_report
from app.shared.versioning import content_hash


def a310_draft(
    run_id,
    version_id,
    facts,
    evidence,
    citations,
    unknowns,
    qualification_refs,
    mode,
    decision_id,
    check_ids,
    reviewer_ids=None,
):
    by_key = {c["source_ref"]: c["citation_id"] for c in citations}
    ids = [row["id"] for row in evidence]

    def cite(*keys):
        return [by_key[key] for key in keys if key in by_key]

    def instruction(index, text, sources, qualified=False, step=None):
        return {
            "instruction_id": f"{version_id}:instruction:{index}:{content_hash(text)[:8]}",
            "order": index,
            "text": text,
            "citation_ids": cite(*sources),
            "evidence_ids": ids if step else [],
            "alarm_step_ref": step,
            "required_qualification": ["MECHANICAL"] if qualified else [],
            "execution_boundary": "AUTHORIZED_PERSONNEL_REQUIRED"
            if qualified
            else "OBSERVATION_ONLY",
            "policy_reference_ids": [ref["policy_reference_id"] for ref in qualification_refs]
            if qualified
            else [],
        }

    leak = facts.get("continuous_leak_sound") is True
    possibilities = [
        (
            "下游管路泄漏",
            ("A310", "H03"),
            "当前已确认持续漏气声，支持优先检查泄漏；具体接头或部位尚未确认。"
            if leak
            else "报警码列出的可能原因；当前无持续漏气声支持，不能确认或排除泄漏。",
        ),
        (
            "过滤器堵塞或调压器异常",
            ("A310", "WO-240-051"),
            "维修记录曾发现滤芯堵塞；该历史维修结果不是本次事实。",
        ),
        ("上游供气不足", ("A310",), "须依据本次上游和设备端压力比较，不能用历史压力补全。"),
    ]
    known = [
        {
            "text": (
                f"{LABELS.get(r['key'], r['key'])}：{format_fact(r['value'])} "
                f"{UNITS.get(r['key'], '')}"
            ).strip(),
            "evidence_version_ids": [r["id"]],
            "status": r["state"],
        }
        for r in evidence
        if not r.get("media_id")
    ]
    expected = {
        "upstream_pressure_mpa": 0.64,
        "device_pressure_mpa": 0.41,
        "continuous_leak_sound": True,
    }

    def compared(key):
        return (
            f"{LABELS.get(key, '持续漏气声')}：本次{format_fact(facts.get(key))}，"
            f"H03为{format_fact(expected[key])}{UNITS.get(key, '')}。"
        )

    report = {
        "report_version_id": version_id,
        "diagnosis_run_id": run_id,
        "status": "FINALIZING" if mode == "PENDING_REVIEW" else "COMPLETED",
        "publication_status": "DRAFT" if mode == "PENDING_REVIEW" else "PUBLISHED",
        "fault_phenomenon": "A310 气压低；当前压力和漏气观察见已知事实。",
        "safety_blocked": False,
        "known_facts": known,
        "confirmed_observations": [
            {
                "text": f"已复核{r['source']}候选：{LABELS.get(r['key'], r['key'])}"
                f"={format_fact(r['value'])}{UNITS.get(r['key'], '')}；"
                f"定位 {r.get('locators', {})}",
                "evidence_version_ids": [r["id"]],
                "status": r["state"],
            }
            for r in evidence
            if r.get("media_id")
        ],
        "unconfirmed_information": [
            {"text": x, "source_refs": [], "reason": "尚未确认"} for x in unknowns
        ]
        + [
            {
                "text": "最终根因和具体泄漏部位未确认",
                "source_refs": [],
                "reason": "AI 只能提出可能原因",
            }
        ],
        "contradictions": [],
        "manual_references": [
            {
                "text": "A310 按上游/设备端压力比较、漏气观察、停机泄压、授权检查的顺序排查。",
                "citation_ids": cite("A310"),
            }
        ],
        "possible_causes": [
            {
                "claim_id": f"{version_id}:cause:{i}",
                "rank": i,
                "cause": cause,
                "status": "POSSIBLE",
                "citation_ids": cite(*refs),
                "supporting_evidence_ids": ids,
                "counter_evidence_ids": [],
                "missing_evidence": ["授权气路检查和本次检漏结果"],
                "ranking_reason": reason,
            }
            for i, (cause, refs, reason) in enumerate(possibilities, 1)
        ],
        "historical_comparisons": [
            {
                "citation_ids": cite("H03"),
                "current_evidence_ids": ids,
                "same_points": ["均为 A310。"]
                + [compared(k) for k, v in expected.items() if facts.get(k) == v],
                "different_points": [
                    "H03 已确认并处理下游接头松动；本次尚未检查，不能确认接头松动。"
                ]
                + [compared(k) for k, v in expected.items() if facts.get(k) != v],
                "missing_information": ["本次具体泄漏部位、维修和复机验证"],
                "effect_on_diagnosis": "历史相似性只支持可能原因；"
                "WO-240-051 是滤芯堵塞的另一个维修例子。",
            }
        ],
        "evidence_sources": citations,
        "policy_references": qualification_refs,
        "immediate_safety_actions": [],
        "safety_preconditions": [
            instruction(
                1,
                "气路拆装前停机、断电、锁定挂牌、隔离气源并确认残余压力释放。",
                ("SAFE-02", "A310"),
            ),
            instruction(
                2, "禁止带压拆装；由相应授权机械人员检查气路。", ("SAFE-03", "SAFE-04"), True
            ),
        ],
        "check_sequence": [
            instruction(
                1,
                "比较本次上游与设备端压力，保留读数，不直接确认根因。",
                ("A310",),
                step="A310:STEP1",
            ),
            instruction(
                2,
                "核对持续漏气声的现场观察；没有观察不能当作没有泄漏。",
                ("A310",),
                step="A310:STEP2",
            ),
            instruction(
                3,
                "进一步气路检查前停机、隔离气源、泄压并锁定挂牌。",
                ("A310", "SAFE-02", "SAFE-03"),
                step="A310:STEP3",
            ),
            instruction(
                4,
                "由授权机械人员检查管路、过滤器和调压器，确认具体故障部位。",
                ("A310", "SAFE-04"),
                True,
                "A310:STEP4",
            ),
        ],
        "missing_information": [
            {
                "question_id": "recent-maintenance",
                "text": "可补充近期气路维修记录。",
                "reason": "非阻断背景信息。",
                "citation_ids": cite("WO-240-051"),
                "related_evidence_ids": [],
                "blocking": False,
            }
        ],
        "stop_conditions": [
            instruction(
                1,
                "出现烟雾、焦味、异常高温、剧烈振动、金属摩擦声或部件松脱时立即停机并升级专家。",
                ("SAFE-01",),
            ),
            instruction(2, "证据矛盾、知识无覆盖或风险不明时停止排查并升级专家。", ("SAFE-05",)),
        ],
        "escalation_reasons": [],
        "escalate_expert": False,
        "evidence_sufficiency": "SUFFICIENT_FOR_POSSIBILITIES",
        "limitations": [
            "FIXTURE/RULE：未调用真实生成模型或外部 Jev，不代表模型诊断质量。",
            "模板批准为明确标记的 fixture 模拟，不代表生产人工审定。",
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
