"""One attempt per call, bounded response, no redirects/proxy or silent mode fallback."""

import asyncio
import ipaddress
import json
from collections.abc import Callable
from typing import Literal
from urllib.parse import urlparse

import httpx

from app.shared.providers.data_profile import ProcessingGrant, ProviderDataProfile
from app.shared.providers.egress import authorize_egress
from app.shared.providers.protocols import ProviderFailure


class ModelTransport:
    def __init__(
        self,
        *,
        mode: Literal["REAL_LOCAL", "REAL_APPROVED_EXTERNAL"],
        profile: ProviderDataProfile,
        permissions: Callable,
        api_key: str | None = None,
        transport=None,
        timeout: float = 15,
    ):
        if mode not in {"REAL_LOCAL", "REAL_APPROVED_EXTERNAL"}:
            raise ValueError("Explicit real mode required")
        if not 0 < timeout <= 30:
            raise ValueError("Request timeout out of bounds")
        self.mode, self.profile, self.permissions = mode, profile, permissions
        self.api_key, self.transport, self.timeout = api_key, transport, timeout

    def authorize(self, payload: dict, purpose: str) -> tuple[ProcessingGrant, ...]:
        grants = self.permissions()
        if not grants or any(not g.readable for g in grants):
            raise ProviderFailure("PROCESSING_DENIED")
        parsed = urlparse(self.profile.endpoint)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderFailure("ENDPOINT_NOT_APPROVED")
        if self.mode == "REAL_LOCAL":
            try:
                local = ipaddress.ip_address(parsed.hostname or "").is_loopback
            except ValueError:
                local = False
            if not local or parsed.scheme not in {"http", "https"} or not self.profile.enabled:
                raise ProviderFailure("LOCAL_ENDPOINT_REQUIRED")
        elif authorize_egress(grants, self.profile, purpose, payload).decision != "ALLOWED":
            raise ProviderFailure("PROCESSING_DENIED")
        elif not self.api_key:
            raise ProviderFailure("PROVIDER_KEY_REQUIRED")
        return grants

    async def post(self, payload: dict, purpose: str) -> dict:
        # The caller supplies server-derived current permissions, not a client consent flag.
        before = self.authorize(payload, purpose)
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=self.timeout,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    # Recheck after client initialization, immediately before any send.
                    if self.authorize(payload, purpose) != before:
                        raise ProviderFailure("PROCESSING_PERMISSION_CHANGED")
                    async with client.stream(
                        "POST",
                        self.profile.endpoint,
                        json=payload,
                        headers=headers,
                    ) as response:
                        if response.status_code == 429:
                            raise ProviderFailure("RATE_LIMITED")
                        if response.status_code >= 500:
                            raise ProviderFailure("TEMPORARY_UNAVAILABLE")
                        if response.status_code != 200:
                            raise ProviderFailure("PROVIDER_HTTP_FAILURE")
                        raw = bytearray()
                        async for block in response.aiter_bytes():
                            raw.extend(block)
                            if len(raw) > 1_000_000:
                                raise ProviderFailure("PROVIDER_RESPONSE_TOO_LARGE")
            if self.authorize(payload, purpose) != before:
                raise ProviderFailure("PROCESSING_PERMISSION_CHANGED")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
            return result
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderFailure("PROVIDER_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure("PROVIDER_TRANSPORT_FAILURE") from exc
        except (ValueError, UnicodeError) as exc:
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID") from exc
        except ProviderFailure:
            raise
        except Exception as exc:
            raise ProviderFailure("PROVIDER_TRANSPORT_FAILURE") from exc


def pinned_model(model: str) -> str:
    if not model or "latest" in model.lower() or model != model.strip():
        raise ValueError("An explicit model version is required")
    return model


def token_usage(body: dict) -> int | None:
    usage = body.get("usage")
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise ProviderFailure("INVALID_USAGE")
    values = [usage.get("prompt_tokens"), usage.get("completion_tokens")]
    if all(v is None for v in values):
        values = [usage.get("input_tokens"), usage.get("output_tokens")]
    total = 0
    for value in values:
        if type(value) is not int or value < 0:
            raise ProviderFailure("INVALID_USAGE")
        total += value
    return total
