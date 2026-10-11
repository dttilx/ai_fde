from types import SimpleNamespace

import pytest

from app.diagnosis.citation_assessment import validate_citations
from app.diagnosis.claim_review import material_claims
from app.diagnosis.models import Citation
from app.shared.errors import DomainError


@pytest.mark.parametrize(
    "field,wrong",
    [
        ("locator", "第9页 / 错误章节"),
        ("source_ref", "FAKE"),
        ("source_type", "APPROVED_CASE"),
        ("checksum", "wrong"),
    ],
)
def test_database_citation_identity_does_not_replace_source_provenance(monkeypatch, field, wrong):
    from hashlib import sha256

    content = "历史案例描述，不确认当前根因。"
    checksum = sha256(content.encode()).hexdigest()
    source = SimpleNamespace(
        release_id="r1",
        source_key="H02",
        collection="HISTORICAL_CASE",
        locator={"page": 6, "section": "历史案例"},
        checksum=checksum,
    )
    payload = {
        "citation_id": "r1:H02",
        "knowledge_release_id": "r1",
        "source_ref": "H02",
        "source_type": "HISTORICAL_CASE",
        "locator": "第6页 / 历史案例",
        "checksum": checksum,
        "excerpt": content,
    }
    record = SimpleNamespace(source_id="source", payload=payload)
    db = SimpleNamespace(get=lambda model, identifier: record if model is Citation else source)
    monkeypatch.setattr(
        "app.diagnosis.citation_assessment.authorized_source_ids", lambda db, actor: ["source"]
    )
    validate_citations(db, None, [payload])
    # Simulate a corrupt stored citation that still matches its incoming ID and quote.
    record.payload = {**payload, field: wrong}
    with pytest.raises(DomainError, match="CITATION_PROVENANCE_INVALID"):
        validate_citations(db, None, [record.payload])


def test_repeated_claim_identifier_is_rejected_instead_of_overwriting_a_claim():
    payload = {
        area: []
        for area in (
            "possible_causes",
            "manual_references",
            "safety_preconditions",
            "check_sequence",
            "stop_conditions",
            "immediate_safety_actions",
            "escalation_reasons",
        )
    }
    payload["possible_causes"] = [{"claim_id": "same"}, {"claim_id": "same"}]
    with pytest.raises(DomainError, match="DUPLICATE_REPORT_CLAIM"):
        material_claims(payload)


@pytest.mark.parametrize("required", [[], ["MECHANICAL"], ["MECHANICAL", "ELECTRICAL"]])
def test_review_qualification_follows_actual_instruction_requirements(required):
    from app.diagnosis.claim_review import required_review_qualifications

    payload = {
        area: []
        for area in (
            "possible_causes",
            "manual_references",
            "safety_preconditions",
            "check_sequence",
            "stop_conditions",
            "immediate_safety_actions",
            "escalation_reasons",
        )
    }
    payload["check_sequence"] = [{"instruction_id": "step1", "required_qualification": required}]
    assert required_review_qualifications(payload) == set(required)
