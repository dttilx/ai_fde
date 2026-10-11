from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IMAGE_COUNT = 5
IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_PIXELS = 25_000_000
VIDEO_COUNT = 1
VIDEO_BYTES = 100 * 1024 * 1024
VIDEO_SECONDS = 60
VIDEO_FRAMES = 8
DECODE_SECONDS = 30


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_evidence_version: int = Field(ge=1)
    decision: Literal["CONFIRMED", "CORRECTED", "REJECTED"]
    corrected_content: dict | None = None
    review_note: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def correction_required(self):
        if not self.review_note.strip():
            raise ValueError("Review note cannot be blank")
        if (self.decision == "CORRECTED") != (self.corrected_content is not None):
            raise ValueError("Only CORRECTED requires corrected_content")
        return self


class EvidenceReview(ReviewDecision):
    evidence_id: str = Field(min_length=1, max_length=36)


class EvidenceExclude(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_evidence_version: int = Field(ge=1)
    review_note: str = Field(min_length=1, max_length=1000)


class ReviewBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decisions: list[EvidenceReview] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_items(self):
        if len({item.evidence_id for item in self.decisions}) != len(self.decisions):
            raise ValueError("Each candidate must have one explicit decision")
        return self
