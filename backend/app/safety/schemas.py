import json
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, model_validator

from app.shared.config import PROJECT_ROOT


@lru_cache
def safety_sources():
    rows = []
    for name in ("safety-rules.json", "alarm-codes.json"):
        rows.extend(
            json.loads((PROJECT_ROOT / "knowledge/seed" / name).read_text(encoding="utf-8"))
        )
    return {row["id"]: row for row in rows}


def rule_citations(ids):
    sources = safety_sources()
    return tuple(
        {
            "source_ref": identifier,
            "page": sources[identifier]["source_page"],
            "section": sources[identifier]["source_section"],
            "source_checksum": sources[identifier]["source_checksum"],
        }
        for identifier in ids
    )


class SafetyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: str
    safety_blocked: bool
    escalate_expert: bool
    rule_ids: tuple[str, ...]
    instructions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    reasons: tuple[str, ...]
    rule_version: str
    citations: tuple[dict, ...] = ()

    @model_validator(mode="after")
    def bind_sources(self):
        object.__setattr__(self, "citations", rule_citations(self.rule_ids))
        return self
