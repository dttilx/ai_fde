from pydantic import BaseModel, ConfigDict, Field


class DiagnosisManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    graph_version: str
    prompt_version: str
    model_versions: dict[str, str]
    knowledge_release_id: str
    evidence_snapshot_hash: str
    citation_ids: tuple[str, ...] = ()
    access_version: str
    egress_version: str
    rubric_version: str
    ranking_version: str
    ledger_id: str
    job_ids: tuple[str, ...] = ()
    checkpoint_version: int = Field(default=0, ge=0)
