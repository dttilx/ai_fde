from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProviderDataProfile:
    provider: str
    endpoint: str
    version: str
    terms_ref: str
    checked_at: datetime
    enabled: bool
    allowed_origins: tuple[str, ...]
    retention_mode: str = "UNVERIFIED"


@dataclass(frozen=True)
class ProcessingGrant:
    policy_id: str
    version: int
    origin: str
    egress: str = "DENY"
    providers: tuple[str, ...] = ()
    purposes: tuple[str, ...] = ()
    basis: str | None = None
    expires_at: datetime | None = None
    readable: bool = False
