from app.knowledge.templates import TemplateSupport
from app.shared.errors import DomainError


def release_mode(
    proof: TemplateSupport,
    *,
    safety_clear: bool,
    force_review: bool,
    has_blocking_questions: bool,
    contradictions: bool,
    access_valid: bool,
) -> str:
    if not safety_clear or contradictions or not access_valid or has_blocking_questions:
        raise DomainError("REPORT_RELEASE_BLOCKED", 409)
    return "AUTO_VALIDATED" if proof.valid and not force_review else "PENDING_REVIEW"
