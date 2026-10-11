from pydantic import BaseModel, ConfigDict, Field


class ExpertOpen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pending_action_id: str
    reason: str = Field(min_length=1, max_length=2000)


class ExpertRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: str = Field(min_length=1, max_length=4000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    report_version_id: str
