import io

import pytest
from PIL import Image
from pydantic import ValidationError

from app.evidence.schemas import EvidenceReview, ReviewBatch
from app.evidence.validation import inspect_media
from app.shared.errors import DomainError


def test_decoded_pixel_budget_is_checked_before_full_decode():
    data = io.BytesIO()
    Image.new("1", (5001, 5000)).save(data, "PNG")
    with pytest.raises(DomainError, match="MEDIA_PIXEL_LIMIT"):
        inspect_media(data.getvalue(), "image/png")


def test_review_has_no_implicit_accept_or_system_unavailable_option():
    with pytest.raises(ValidationError):
        EvidenceReview(evidence_id="x", expected_evidence_version=1, review_note="checked")
    with pytest.raises(ValidationError):
        EvidenceReview(
            evidence_id="x",
            expected_evidence_version=1,
            decision="UNAVAILABLE",
            review_note="checked",
        )
    with pytest.raises(ValidationError):
        ReviewBatch(decisions=[])
