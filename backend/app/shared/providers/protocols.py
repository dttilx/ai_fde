from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ProviderResult:
    mode: Literal["FIXTURE", "REAL_LOCAL", "REAL_APPROVED_EXTERNAL"]
    model: str
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    token_usage: int | None = None


class Provider(Protocol):
    async def invoke(self, payload: dict[str, Any]) -> ProviderResult: ...


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> ProviderResult: ...


class ProviderFailure(Exception):
    """Safe failure code, never remote response text."""
