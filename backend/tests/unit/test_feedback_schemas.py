import pytest
from pydantic import ValidationError

from app.feedback.schemas import CaseReviewInput, RepairInput


def test_repair_requires_explicit_restart_state_and_case_decision():
    assert RepairInput(diagnosis_run_id="r", report_version_id="v").restart_validation == "UNKNOWN"
    with pytest.raises(ValidationError):
        CaseReviewInput(decision="APPROVE", note="", deidentification_status="PASSED")
    with pytest.raises(ValidationError):
        RepairInput(diagnosis_run_id="r", report_version_id="v", restart_validation="MAYBE")
