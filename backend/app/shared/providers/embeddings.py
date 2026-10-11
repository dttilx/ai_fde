"""Versioned real embeddings, with explicit failure instead of hash-vector substitution."""

import math

from app.shared.providers.http_gateway import ModelTransport, pinned_model, token_usage
from app.shared.providers.protocols import ProviderFailure, ProviderResult


class ModelEmbeddings:
    def __init__(self, model: str, dimensions: int, transport: ModelTransport):
        if not 1 <= dimensions <= 4096:
            raise ValueError("Embedding dimension out of bounds")
        self.model, self.dimensions, self.transport = pinned_model(model), dimensions, transport

    async def embed(self, texts: list[str]) -> ProviderResult:
        if not 1 <= len(texts) <= 32 or any(
            not isinstance(t, str) or not t.strip() or len(t) > 12000 for t in texts
        ):
            raise ProviderFailure("EMBEDDING_INPUT_INVALID")
        body = await self.transport.post(
            {"model": self.model, "input": texts, "encoding_format": "float"}, "KNOWLEDGE_EMBEDDING"
        )
        if body.get("model") != self.model:
            raise ProviderFailure("MODEL_OR_MODE_MISMATCH")
        rows = body.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ProviderFailure("EMBEDDING_RESPONSE_INVALID")
        vectors: list[list[float] | None] = [None] * len(texts)
        for row in rows:
            if not isinstance(row, dict):
                raise ProviderFailure("EMBEDDING_RESPONSE_INVALID")
            index, vector = row.get("index"), row.get("embedding")
            if type(index) is not int or not 0 <= index < len(texts) or vectors[index] is not None:
                raise ProviderFailure("EMBEDDING_RESPONSE_INVALID")
            if (
                not isinstance(vector, list)
                or len(vector) != self.dimensions
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
                or not any(v != 0 for v in vector)
            ):
                raise ProviderFailure("EMBEDDING_RESPONSE_INVALID")
            vectors[index] = vector
        return ProviderResult(
            self.transport.mode,
            self.model,
            "SUCCEEDED",
            {"vectors": vectors, "dimensions": self.dimensions},
            token_usage=token_usage(body),
        )
