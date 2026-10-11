from app.shared.errors import DomainError
from app.shared.providers.fixtures import FixtureProvider

CAPABILITIES = {
    "llm",
    "embedding",
    "ocr",
    "vision",
    "qr",
    "video",
    "jev_passage",
    "jev_claim",
    "reranking",
}


def fixture_provider(capability: str) -> FixtureProvider:
    if capability not in CAPABILITIES:
        raise DomainError("UNKNOWN_PROVIDER_CAPABILITY")
    return FixtureProvider(capability)
