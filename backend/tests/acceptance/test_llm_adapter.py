import asyncio
import copy
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.shared.providers.data_profile import ProcessingGrant, ProviderDataProfile
from app.shared.providers.http_gateway import ModelTransport
from app.shared.providers.llm import StructuredLLM
from app.shared.providers.protocols import ProviderFailure
from tests.acceptance.test_a203 import create


def llm(handler):
    profile = ProviderDataProfile(
        "generator",
        "http://127.0.0.1:11434/v1/chat/completions",
        "local-test-v1",
        "MOCK_ONLY",
        datetime.now(UTC),
        True,
        ("EXAM_SOURCE",),
    )
    grant = ProcessingGrant("local-readable", 1, "EXAM_SOURCE", readable=True)
    transport = ModelTransport(
        mode="REAL_LOCAL",
        profile=profile,
        permissions=lambda: (grant,),
        transport=httpx.MockTransport(handler),
    )
    return StructuredLLM("test-generator-v1", transport)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("NONE", None),
        ("SAFETY", "GENERATION_CHANGED_TRUSTED_FIELDS"),
        ("BAD_JSON", "PROVIDER_RESPONSE_INVALID"),
        ("BAD_MODEL", "MODEL_OR_MODE_MISMATCH"),
        ("TRUNCATED", "GENERATION_INCOMPLETE"),
        ("BAD_CITATION", "PROVIDER_RESPONSE_INVALID"),
    ],
)
async def test_real_protocol_has_no_success_fallback_or_release_authority(mutation, expected):
    client, started = await asyncio.to_thread(create, force=True)
    original = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()["report"]
    draft = copy.deepcopy(original)
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        report = copy.deepcopy(draft)
        if mutation == "SAFETY":
            report["safety_preconditions"][0]["text"] += " 偷换安全要求"
        elif mutation == "BAD_CITATION":
            report["possible_causes"][0]["citation_ids"] = ["invented"]
        return httpx.Response(
            200,
            json={
                "model": "other" if mutation == "BAD_MODEL" else "test-generator-v1",
                "choices": [
                    {
                        "finish_reason": "length" if mutation == "TRUNCATED" else "stop",
                        "message": {
                            "content": "oops" if mutation == "BAD_JSON" else json.dumps(report)
                        },
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    if expected:
        with pytest.raises(ProviderFailure, match=expected):
            await llm(handler).generate(draft)
    else:
        result = await llm(handler).generate(draft)
        assert result.mode == "REAL_LOCAL" and result.status == "DRAFT_REQUIRES_REVIEW"
        assert result.data["report"]["publication_status"] == "DRAFT"
        assert result.token_usage == 30
    assert len(calls) == 1 and draft == original
