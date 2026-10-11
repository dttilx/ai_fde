from dataclasses import dataclass

from app.access.models import PolicyBinding


@dataclass(frozen=True)
class DerivedPolicy:
    readable_by: frozenset[str]
    egress: str
    basis_ids: tuple[str, ...]


def derive_policy(contributors: list[PolicyBinding]) -> DerivedPolicy:
    if not contributors:
        return DerivedPolicy(frozenset(), "DENY", ())
    readers = set(contributors[0].readable_by)
    for policy in contributors[1:]:
        readers.intersection_update(policy.readable_by)
    # External approval is checked per contributor/provider/purpose, not inherited by masking.
    egress = (
        "DENY" if any(p.egress == "DENY" or not p.basis for p in contributors) else "CHECK_REQUIRED"
    )
    return DerivedPolicy(frozenset(readers), egress, tuple(p.id for p in contributors))
