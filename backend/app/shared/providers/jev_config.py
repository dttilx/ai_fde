"""Explicit private deployment profile; no inferred external-processing approval."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictBool

from app.shared.config import settings
from app.shared.errors import DomainError
from app.shared.providers.data_profile import ProviderDataProfile
from app.shared.providers.http_gateway import ModelTransport
from app.shared.providers.jev import (
    FixtureJevClaimEvaluator,
    FixtureJevEvaluator,
    SystemOneEvaluator,
)


class JevProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    terms_ref: str
    checked_at: datetime
    enabled: StrictBool
    allowed_origins: list[str]
    retention_mode: str
    model: str


def configured_evaluator(*, claim=False):
    cfg = settings()
    if cfg.provider_mode == "FIXTURE":
        return FixtureJevClaimEvaluator() if claim else FixtureJevEvaluator()
    if cfg.provider_mode != "REAL_APPROVED_EXTERNAL" or not cfg.jev_api_key or not cfg.jev_model:
        return None
    try:
        record = JevProfile.model_validate(
            json.loads(cfg.jev_profile_path.read_text(encoding="utf-8"))
        )
        if (
            not record.enabled
            or not record.version
            or not record.terms_ref
            or record.retention_mode == "UNVERIFIED"
            or record.model != cfg.jev_model
            or record.checked_at.tzinfo is None
            or not record.allowed_origins
        ):
            raise ValueError("Unverified profile")
    except (OSError, ValueError):
        raise DomainError("JEV_PROFILE_NOT_VERIFIED", 409) from None
    profile = ProviderDataProfile(
        "jev",
        "https://api.typesafe.ai/v1/systemone",
        record.version,
        record.terms_ref,
        record.checked_at,
        True,
        tuple(record.allowed_origins),
        record.retention_mode,
    )
    # Per-incident permissions are injected by the persistent assessment runtime before each call.
    transport = ModelTransport(
        mode="REAL_APPROVED_EXTERNAL",
        profile=profile,
        permissions=lambda: (),
        api_key=cfg.jev_api_key.get_secret_value(),
        timeout=3,
    )
    return SystemOneEvaluator(cfg.jev_model, transport, claim=claim)
