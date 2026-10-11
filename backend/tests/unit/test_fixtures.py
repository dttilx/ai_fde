import pytest

from app.shared.providers.protocols import ProviderFailure
from app.shared.providers.registry import CAPABILITIES, fixture_provider


@pytest.mark.parametrize("capability", sorted(CAPABILITIES))
async def test_fixture_modes_and_failure(capability):
    provider = fixture_provider(capability)
    assert await provider.invoke({}) == await provider.invoke({})
    assert (await provider.invoke({})).mode == "FIXTURE"
    with pytest.raises(ProviderFailure):
        await provider.invoke({"fixture_failure": True})


async def test_embedding_shape_is_explicitly_nonsemantic():
    value = await fixture_provider("embedding").embed(["A203"])
    assert len(value.data["vectors"][0]) == 16
    assert value.limitations


@pytest.mark.parametrize("capability", ["ocr", "vision", "qr", "video"])
async def test_unknown_media_returns_no_fabricated_observation(capability):
    result = await fixture_provider(capability).invoke({"media_key": "unknown-test-upload"})
    assert result.status == "UNAVAILABLE"
    assert result.data["candidates"] == []


async def test_jev_fixture_never_claims_semantic_support():
    result = await fixture_provider("jev_claim").invoke({"claim": "unknown hypothetical cause"})
    assert result.data["relation"] == "UNKNOWN"
