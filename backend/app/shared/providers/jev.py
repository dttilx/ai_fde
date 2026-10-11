from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.providers.fixtures import FixtureProvider
from app.shared.providers.jev_payload import validate_projection


class JevJudgment(BaseModel):
    """Local normalized adapter contract, not an assertion about Jev's wire response."""

    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, revalidate_instances="always", validate_assignment=True
    )
    relevance_level: int | None = Field(default=None, strict=True, ge=0, le=3)
    category: Literal[
        "TECHNICAL_EVIDENCE",
        "HISTORICAL_REFERENCE",
        "BACKGROUND",
        "UNRELATED",
        "CONFLICT_REVIEW",
        "UNKNOWN",
    ] = "UNKNOWN"
    confidence: float | None = Field(default=None, strict=True, ge=0, le=1)
    probabilities: dict[str, float] | None = None
    instruction_signal: Literal["TRUE", "FALSE", "UNKNOWN"] = "UNKNOWN"

    @field_validator("probabilities", mode="before")
    @classmethod
    def strict_probabilities(cls, value):
        if value is not None and (
            not isinstance(value, dict)
            or any(type(number) not in (int, float) for number in value.values())
        ):
            raise ValueError("Probabilities must be numerical, not strings or booleans")
        return value

    @model_validator(mode="after")
    def valid_distribution(self):
        if self.probabilities is not None:
            options = {
                "TECHNICAL_EVIDENCE",
                "HISTORICAL_REFERENCE",
                "BACKGROUND",
                "UNRELATED",
                "CONFLICT_REVIEW",
                "UNKNOWN",
            }
            if (
                set(self.probabilities) != options
                or any(not 0 <= value <= 1 for value in self.probabilities.values())
                or abs(sum(self.probabilities.values()) - 1) > 1e-6
            ):
                raise ValueError("Invalid choice distribution")
            if self.probabilities[self.category] < max(self.probabilities.values()):
                raise ValueError("Choice conflicts with its distribution")
        return self


@dataclass(frozen=True)
class JevEvaluation:
    judgment: JevJudgment
    actual_model: str
    mode: Literal["FIXTURE", "REAL"]
    token_usage: int | None


class JevEvaluator(Protocol):
    model: str
    mode: str

    async def evaluate(self, projection: dict) -> JevEvaluation: ...


class JevClaimJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, revalidate_instances="always")
    relation: Literal["SUPPORTS", "CONTRADICTS", "UNSUPPORTED", "UNKNOWN"] = "UNKNOWN"
    confidence: float | None = Field(default=None, strict=True, ge=0, le=1)


@dataclass(frozen=True)
class JevClaimEvaluation:
    judgment: JevClaimJudgment
    actual_model: str
    mode: Literal["FIXTURE", "REAL"]
    token_usage: int | None


class FixtureJevClaimEvaluator:
    model = "fixture-jev_claim-v1"
    mode = "FIXTURE"

    async def evaluate(self, projection: dict) -> JevClaimEvaluation:
        validate_projection(projection)
        result = await FixtureProvider("jev_claim").invoke(projection)
        return JevClaimEvaluation(JevClaimJudgment(), result.model, "FIXTURE", result.token_usage)


class FixtureJevEvaluator:
    model = "fixture-jev_passage-v1"
    mode = "FIXTURE"

    async def evaluate(self, projection: dict) -> JevEvaluation:
        validate_projection(projection)
        result = await fixture_jev().invoke(projection)
        # Explicit UNKNOWN; no relevance score or safety approval is fabricated.
        return JevEvaluation(JevJudgment(), result.model, "FIXTURE", result.token_usage)


def fixture_jev() -> FixtureProvider:
    """Local workflow fixture only; real System One HTTP is introduced by T066."""
    return FixtureProvider("jev_passage")


class SystemOneEvaluator:
    """Exactly one authorized HTTP attempt; the shared runtime owns retry/budget policy."""

    mode = "REAL"

    def __init__(self, model: str, transport, *, claim=False):
        from app.shared.providers.http_gateway import pinned_model

        self.model = pinned_model(model)
        if not self.model.startswith("jev-"):
            raise ValueError("Explicit Jev model required")
        if transport.mode != "REAL_APPROVED_EXTERNAL" or (
            transport.profile.provider != "jev"
            or transport.profile.endpoint != "https://api.typesafe.ai/v1/systemone"
        ):
            raise ValueError("Official System One endpoint and external profile required")
        self.transport, self.profile, self.claim = transport, transport.profile, claim

    def with_permissions(self, callback):
        from app.shared.providers.http_gateway import ModelTransport

        old = self.transport
        transport = ModelTransport(
            mode=old.mode,
            profile=old.profile,
            permissions=callback,
            api_key=old.api_key,
            transport=old.transport,
            timeout=old.timeout,
        )
        return SystemOneEvaluator(self.model, transport, claim=self.claim)

    async def evaluate(self, projection: dict):
        import math

        from app.shared.providers.jev_response import parse_answers
        from app.shared.providers.protocols import ProviderFailure

        validate_projection(projection)
        required = (
            {"support_relation"}
            if self.claim
            else {
                "relevance",
                "applicability",
                "instruction_signal",
            }
        )
        if projection["model"] != self.model or set(projection["questions"]) != required:
            raise ProviderFailure("JEV_REQUEST_INVALID")
        purpose = "CLAIM_SUPPORT" if self.claim else "PASSAGE_RELEVANCE"
        body = await self.transport.post(projection, purpose)
        answers, usage = parse_answers(body, projection)
        if self.claim:
            relation = answers["support_relation"]
            return JevClaimEvaluation(
                JevClaimJudgment(relation=relation["choice"], confidence=relation["confidence"]),
                self.model,
                "REAL",
                usage,
            )
        category = answers["applicability"]
        signal = answers["instruction_signal"]["noul"]
        judgment = JevJudgment(
            # A fractional expected score is rounded down, never overstated as certainty.
            relevance_level=math.floor(answers["relevance"]["score"]),
            category=category["choice"],
            confidence=category["confidence"],
            probabilities=category["probabilities"],
            instruction_signal="TRUE" if signal >= 0.9 else "FALSE" if signal <= 0.1 else "UNKNOWN",
        )
        return JevEvaluation(judgment, self.model, "REAL", usage)
