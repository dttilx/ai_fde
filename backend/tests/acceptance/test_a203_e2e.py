"""Independent A203 demo gate; delegates to the already exercised fixture flow."""

from tests.acceptance.test_a203 import (
    test_a203_checkpoint_review_resume_and_duplicate_guard as force_review_flow,
)
from tests.acceptance.test_a203 import (
    test_a203_report_safe_order_sources_and_private_assessment as auto_flow,
)


def test_a203_demo_auto_path():
    auto_flow()


def test_a203_demo_force_review_path():
    force_review_flow()
