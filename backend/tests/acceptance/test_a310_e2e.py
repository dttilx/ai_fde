"""Independent A310 information-question regression."""

from tests.acceptance.test_a310 import (
    test_three_source_bound_questions_partial_resume_and_auto_report as a310_flow,
)


def test_a310_demo_path():
    a310_flow()
