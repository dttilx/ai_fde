from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RepairInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diagnosis_run_id: str
    report_version_id: str
    executor_id: str | None = None
    confirmed_root_cause: str | None = Field(default=None, max_length=1000)
    confirmation_ref: str | None = None
    repair_action: str | None = Field(default=None, max_length=2000)
    repair_evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    qualification_refs: list[str] = Field(default_factory=list, max_length=20)
    restart_validation: Literal["UNKNOWN", "FAILED", "PASSED"] = "UNKNOWN"
    restart_evidence_ids: list[str] = Field(default_factory=list, max_length=50)


class SharingScope(BaseModel):
    """Small, explicit sharing scope for an approved case.

    IDs are server-checked against the incident readers; arbitrary policy
    expressions are intentionally not accepted from the browser.
    """

    model_config = ConfigDict(extra="forbid")
    reader_user_ids: list[str] = Field(default_factory=list, max_length=100)


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_reviewer_id: str
    requested_scope: SharingScope = Field(default_factory=SharingScope)


class CaseReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["APPROVE", "REJECT"]
    note: str = Field(min_length=1, max_length=2000)
    deidentification_status: Literal["PASSED", "FAILED"]
    approved_scope: SharingScope = Field(default_factory=SharingScope)
    publish_on_approval: bool = False


class PublishInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: SharingScope = Field(default_factory=SharingScope)
