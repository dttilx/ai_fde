from typing import TypedDict

STATES = {
    "PREPARING",
    "SAFETY_CHECK",
    "RETRIEVING",
    "NEEDS_INFORMATION",
    "WAITING_EXPERT",
    "CONFLICT_BLOCKED",
    "FINALIZING",
    "COMPLETED",
    "ESCALATED",
    "FAILED",
}


class DiagnosisState(TypedDict, total=False):
    diagnosis_run_id: str
    raw_text: str
    facts: dict
    qualifications: tuple[str, ...]
    status: str
    safety: dict
    evidence_snapshot_hash: str
    retrieved: list[dict]
    needed_information: bool
    question: str
    expert_disposition: dict
    report: dict
    citation_payloads: list[dict]
    assessment: dict
    missing_fields: list[str]
