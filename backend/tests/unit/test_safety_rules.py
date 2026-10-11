import pytest

from app.safety.rules import DANGERS, RULES
from app.safety.service import evaluate


@pytest.mark.parametrize("danger", DANGERS)
def test_danger_is_immediate_and_non_overridable(danger):
    decision = evaluate(f"设备出现{danger}", {})
    assert decision.status == "STOP_AND_ESCALATE"
    assert decision.safety_blocked and decision.escalate_expert
    assert "SAFE-01" in decision.rule_ids


def test_all_rules_and_a205_alarm_alone():
    assert [rule.rule_id for rule in RULES] == [f"SAFE-0{i}" for i in range(1, 6)]
    assert evaluate("", {"alarm_code": "A205"}).safety_blocked
    assert evaluate("", {"smoke": True}).safety_blocked


def test_negation_uncertainty_and_historical_observation():
    assert evaluate("无焦味", {}).status == "CLEAR"
    assert evaluate("不确定是不是焦味", {}).status == "RISK_UNKNOWN"
    assert evaluate("昨天有焦味，现已停机", {}).escalate_expert


def test_conflict_and_no_coverage_block():
    assert evaluate("", {}, contradictions=("不同温度读数",)).status == "CONFLICT_BLOCKED"
    assert evaluate("", {}, coverage=False).safety_blocked


def test_prohibitions_isolation_and_qualification():
    assert evaluate("能不能绕过安全门", {}).safety_blocked
    assert evaluate("", {}, requested_actions=("检查线路",)).safety_blocked
    qualified = evaluate("", {}, ("ELECTRICAL",), ("检查线路",))
    assert qualified.status == "CLEAR"
    assert "SAFE-02" in qualified.rule_ids
    assert evaluate("", {}, requested_actions=("气路拆装",)).safety_blocked
    assert evaluate("", {}, ("MECHANICAL",), ("气路拆装",)).status == "CLEAR"
