import asyncio
import hashlib
from typing import Any

from app.shared.providers.protocols import ProviderFailure, ProviderResult


class FixtureProvider:
    def __init__(self, capability: str):
        self.capability = capability

    async def invoke(self, payload: dict[str, Any]) -> ProviderResult:
        if payload.get("fixture_failure"):
            raise ProviderFailure("FIXTURE_FAILURE")
        if payload.get("fixture_delay"):
            await asyncio.sleep(float(payload["fixture_delay"]))
        # A fixture cannot pretend to observe an arbitrary uploaded image or video.
        data: dict[str, Any] = {"capability": self.capability}
        status = "FIXTURE"
        if self.capability in {"ocr", "vision", "qr", "video"}:
            status = "UNAVAILABLE"
            data["candidates"] = []
        if self.capability in {"jev_passage", "jev_claim", "reranking"}:
            data.update(relation="UNKNOWN", route="PRESERVED")
        return ProviderResult(
            mode="FIXTURE",
            model=f"fixture-{self.capability}-v1",
            status=status,
            data=data,
            limitations=("Deterministic fixture; no real perception or reasoning.",),
            token_usage=0,
        )

    async def embed(self, texts: list[str]) -> ProviderResult:
        vectors = [
            [(value - 127.5) / 127.5 for value in hashlib.sha256(text.encode()).digest()[:16]]
            for text in texts
        ]
        return ProviderResult(
            mode="FIXTURE",
            model="fixture-hash16-v1",
            status="FIXTURE",
            data={"vectors": vectors, "dimensions": 16},
            token_usage=0,
            limitations=("Hash vectors test plumbing; not semantic embeddings.",),
        )
