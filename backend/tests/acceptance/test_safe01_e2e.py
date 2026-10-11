"""Independent SAFE-01 stop/escalation regression."""

from tests.acceptance.test_safety import (
    test_high_risk_notice_is_cited_and_expert_acknowledgement_never_retrieves as safe01_flow,
)

pytest_plugins = ["tests.acceptance.test_safety"]


def test_safe01_demo_path(stopped):
    safe01_flow(stopped)
