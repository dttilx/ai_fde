from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.shared.providers.data_profile import ProcessingGrant, ProviderDataProfile
from app.shared.providers.jev_payload import validate_projection
from app.shared.versioning import content_hash


@dataclass(frozen=True)
class EgressReceipt:
    decision: str
    reason: str
    provider: str
    policy_refs: tuple[str, ...]
    input_hash: str | None = None
    profile_version: str | None = None


def authorize_egress(
    grants: tuple[ProcessingGrant, ...], profile: ProviderDataProfile, purpose: str, payload: dict
) -> EgressReceipt:
    refs = tuple(f"{g.policy_id}:{g.version}" for g in grants)

    def deny(reason: str) -> EgressReceipt:
        return EgressReceipt("SKIPPED_POLICY", reason, profile.provider, refs)

    if not grants or not profile.enabled or not profile.terms_ref or not profile.version:
        return deny("MISSING_PROCESSING_BASIS")
    endpoint = urlparse(profile.endpoint)
    if endpoint.scheme != "https" or endpoint.username or endpoint.password:
        return deny("ENDPOINT_NOT_APPROVED")
    if profile.provider == "jev" and profile.endpoint != "https://api.typesafe.ai/v1/systemone":
        return deny("ENDPOINT_NOT_APPROVED")
    clock = datetime.now(UTC)
    for grant in grants:
        if (
            not grant.readable
            or grant.egress != "APPROVED_REDACTED"
            or not grant.basis
            or grant.expires_at is None
            or grant.expires_at <= clock
            or profile.provider not in grant.providers
            or purpose not in grant.purposes
            or grant.origin not in profile.allowed_origins
        ):
            return deny("INPUT_NOT_APPROVED")
    if profile.provider == "jev":
        from app.shared.errors import DomainError

        try:
            validate_projection(payload)
        except DomainError as exc:
            return deny(exc.code)
    # Receipt intentionally omits payload text and lineage IDs outside local policy refs.
    return EgressReceipt(
        "ALLOWED",
        "APPROVED_MINIMAL_PROJECTION",
        profile.provider,
        refs,
        content_hash(payload),
        profile.version,
    )
