"""Pure HTTP contract checks which do not require a live database."""

import pytest
from pydantic import ValidationError

from app.diagnosis.schemas import RetryInput
from app.feedback.schemas import CaseReviewInput, DraftInput, SharingScope


def test_case_scope_is_explicit_user_ids_only():
    draft = DraftInput(
        assigned_reviewer_id="reviewer-1", requested_scope={"reader_user_ids": ["u-1"]}
    )
    assert draft.requested_scope == SharingScope(reader_user_ids=["u-1"])


def test_case_scope_rejects_arbitrary_policy_fields():
    with pytest.raises(ValidationError):
        DraftInput(assigned_reviewer_id="reviewer-1", requested_scope={"model": "APX-240"})


def test_case_review_requires_explicit_deidentification_and_scope():
    with pytest.raises(ValidationError):
        CaseReviewInput(decision="APPROVE", note="已核对")
    review = CaseReviewInput(
        decision="APPROVE",
        note="已核对",
        deidentification_status="PASSED",
        approved_scope={"reader_user_ids": ["u-1"]},
    )
    assert review.approved_scope.reader_user_ids == ["u-1"]


def test_case_publication_retry_requires_only_expected_status_version():
    assert RetryInput(expected_status_version=3).expected_status_version == 3
    with pytest.raises(ValidationError):
        RetryInput(expected_status_version=-1)
    with pytest.raises(ValidationError):
        RetryInput(expected_status_version=3, unexpected="ignored")
