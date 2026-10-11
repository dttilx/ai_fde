from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    force_review: bool = False


class CancelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_status_version: int = Field(ge=0)


class RetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_status_version: int = Field(ge=0)


class LinkedRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_scope: list[str] = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)


class ResumeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_checkpoint_version: int = Field(ge=0)
    interrupt_id: str
    idempotency_key: str = Field(min_length=1, max_length=100)
    type: Literal["INFORMATION", "REPORT_REVIEW", "EXPERT", "HIGH_RISK"]
    answers: dict = Field(default_factory=dict)
    report_version_id: str | None = None
    report_hash: str | None = None
    claim_review_ids: list[str] = Field(default_factory=list)
    resolution: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def exclusive_payload(self):
        if self.type == "INFORMATION":
            valid = bool(self.answers) and not (
                self.report_hash
                or self.report_version_id
                or self.claim_review_ids
                or self.resolution
            )
        elif self.type == "REPORT_REVIEW":
            valid = bool(self.report_hash and self.report_version_id) and not (
                self.answers or self.resolution
            )
        else:
            valid = bool(self.resolution) and not (
                self.answers or self.report_hash or self.report_version_id or self.claim_review_ids
            )
        if not valid:
            raise ValueError("Payload must match exactly one interrupt type")
        return self
