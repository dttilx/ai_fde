import pytest

from app.diagnosis.release_policy import release_mode
from app.knowledge.templates import TemplateSupport
from app.shared.errors import DomainError

GOOD = TemplateSupport(True, "reference-fixture", ())


@pytest.mark.parametrize(
    "gate", ["safety_clear", "access_valid", "has_blocking_questions", "contradictions"]
)
def test_each_blocking_gate_rejects_even_an_eligible_template(gate):
    conditions = {
        "safety_clear": True,
        "access_valid": True,
        "has_blocking_questions": False,
        "contradictions": False,
        "force_review": False,
    }
    conditions[gate] = not conditions[gate]
    with pytest.raises(DomainError, match="REPORT_RELEASE_BLOCKED"):
        release_mode(GOOD, **conditions)


def test_invalid_proof_and_explicit_review_cannot_auto_publish():
    conditions = {
        "safety_clear": True,
        "access_valid": True,
        "has_blocking_questions": False,
        "contradictions": False,
    }
    bad = TemplateSupport(False, "reference-fixture", ("actual_temperature_c",))
    assert release_mode(bad, force_review=False, **conditions) == "PENDING_REVIEW"
    assert release_mode(GOOD, force_review=True, **conditions) == "PENDING_REVIEW"
