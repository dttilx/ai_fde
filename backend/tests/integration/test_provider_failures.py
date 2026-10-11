import asyncio

import pytest

from app.shared.providers.protocols import ProviderFailure
from tests.unit.test_model_transport import gateway


async def fail_after_permission(transport):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider body must not escape")

    with pytest.raises(ProviderFailure, match="PROVIDER_TRANSPORT_FAILURE"):
        await transport.__class__(
            mode=transport.mode,
            profile=transport.profile,
            permissions=transport.permissions,
            api_key=transport.api_key,
            transport=__import__("httpx").MockTransport(handler),
            timeout=0.5,
        ).post({}, "KNOWLEDGE_EMBEDDING")
    assert calls == 1


def test_transport_provider_failure_is_explicit_and_bounded():
    asyncio.run(fail_after_permission(gateway(lambda request: None)))
