import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.shared.providers.data_profile import ProcessingGrant, ProviderDataProfile
from app.shared.providers.embeddings import ModelEmbeddings
from app.shared.providers.http_gateway import ModelTransport
from app.shared.providers.protocols import ProviderFailure


def gateway(handler, *, allowed=True, mode="REAL_APPROVED_EXTERNAL", **kwargs):
    grant = ProcessingGrant(
        "policy",
        1,
        "SELF_AUTHORED_SIMULATION",
        "APPROVED_REDACTED" if allowed else "DENY",
        ("embedding",),
        ("KNOWLEDGE_EMBEDDING",),
        "self-authored",
        datetime.now(UTC) + timedelta(hours=1),
        True,
    )
    endpoint = (
        "http://127.0.0.1:11434/v1/embeddings"
        if mode == "REAL_LOCAL"
        else "https://example.invalid/v1/embeddings"
    )
    profile = ProviderDataProfile(
        "embedding", endpoint, "v1", "test-only", datetime.now(UTC), True, (grant.origin,)
    )
    return ModelTransport(
        mode=mode,
        profile=profile,
        permissions=lambda: (grant,),
        api_key="unit-only-not-real",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


async def test_denied_embedding_sends_no_request_even_after_masking():
    requests = []
    adapter = ModelEmbeddings(
        "test-embedding-v1", 2, gateway(lambda req: requests.append(req), allowed=False)
    )
    with pytest.raises(ProviderFailure, match="PROCESSING_DENIED"):
        await adapter.embed(["masked"])
    assert requests == []


async def test_real_local_vectors_preserve_order_and_truthful_mode():
    adapter = ModelEmbeddings(
        "test-embedding-v1",
        2,
        gateway(
            lambda req: httpx.Response(
                200,
                json={
                    "model": "test-embedding-v1",
                    "data": [
                        {"index": 1, "embedding": [0, 1]},
                        {"index": 0, "embedding": [1, 0]},
                    ],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 0},
                },
            ),
            mode="REAL_LOCAL",
        ),
    )
    result = await adapter.embed(["甲", "乙"])
    assert result.data["vectors"] == [[1, 0], [0, 1]] and result.mode == "REAL_LOCAL"
    assert result.model == "test-embedding-v1" and result.token_usage == 3


@pytest.mark.parametrize(
    "body",
    [
        {"model": "other", "data": []},
        {"model": "test-embedding-v1", "data": [{"index": 0, "embedding": [1]}]},
        {"model": "test-embedding-v1", "data": [{"index": 0, "embedding": [True, 0]}]},
        {"model": "test-embedding-v1", "data": [{"index": 0, "embedding": [0, 0]}]},
    ],
)
async def test_invalid_vectors_never_return_fixture_success(body):
    adapter = ModelEmbeddings(
        "test-embedding-v1", 2, gateway(lambda req: httpx.Response(200, json=body))
    )
    with pytest.raises(ProviderFailure):
        await adapter.embed(["甲"])


async def test_timeout_is_one_attempt_and_not_success():
    requests = []

    async def slow(req):
        requests.append(req)
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={})

    transport = gateway(slow, timeout=0.01)
    with pytest.raises(ProviderFailure, match="PROVIDER_TIMEOUT"):
        await transport.post({}, "KNOWLEDGE_EMBEDDING")
    assert len(requests) == 1


async def test_redirect_is_not_followed():
    requests = []

    def redirect(req):
        requests.append(req)
        return httpx.Response(307, headers={"Location": "https://unapproved.invalid"})

    with pytest.raises(ProviderFailure, match="PROVIDER_HTTP_FAILURE"):
        await gateway(redirect).post({}, "KNOWLEDGE_EMBEDDING")
    assert len(requests) == 1
