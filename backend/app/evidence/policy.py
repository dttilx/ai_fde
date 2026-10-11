"""Derived versions retain source policy; current parent permissions remain authoritative."""

from sqlalchemy import select

from app.access.models import PolicyBinding
from app.shared.errors import DomainError


def bind_evidence_policy(db, evidence, media_id):
    parent = db.scalar(
        select(PolicyBinding).where(
            PolicyBinding.resource_type == "MEDIA", PolicyBinding.resource_id == media_id
        )
    )
    if parent is None:
        raise DomainError("MEDIA_POLICY_MISSING", 409)
    original = (
        db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "EVIDENCE",
                PolicyBinding.resource_id == evidence.supersedes_id,
            )
        )
        if evidence.supersedes_id
        else None
    )
    readers = set(parent.readable_by)
    providers = set(parent.approved_providers)
    purposes = set(parent.approved_purposes)
    expiry = parent.expires_at
    if original:
        readers.intersection_update(original.readable_by)
        providers.intersection_update(original.approved_providers)
        purposes.intersection_update(original.approved_purposes)
        expiry = (
            min(expiry, original.expires_at)
            if expiry is not None and original.expires_at is not None
            else None
        )
    db.add(
        PolicyBinding(
            resource_type="EVIDENCE",
            resource_id=evidence.id,
            classification=parent.classification,
            origin=original.origin if original else parent.origin,
            readable_by=sorted(readers),
            egress="DENY" if original and original.egress == "DENY" else parent.egress,
            approved_providers=sorted(providers),
            approved_purposes=sorted(purposes),
            basis=parent.basis if not original else original.basis,
            expires_at=expiry,
        )
    )


def require_evidence_read(db, actor, evidence):
    if not evidence.media_id:
        return
    from app.evidence.service import accessible_media

    accessible_media(db, actor, evidence.media_id)
    # Every original/corrected version remains an authoritative contributor.
    # Revoking an original must also revoke access through a later derived version.
    from app.incidents.models import Evidence

    current = evidence
    seen = set()
    while current:
        if current.id in seen:
            raise DomainError("EVIDENCE_LINEAGE_INVALID", 409)
        seen.add(current.id)
        policy = db.scalar(
            select(PolicyBinding)
            .where(
                PolicyBinding.resource_type == "EVIDENCE", PolicyBinding.resource_id == current.id
            )
            .execution_options(populate_existing=True)
        )
        if policy is None or actor.id not in policy.readable_by:
            raise DomainError("NOT_FOUND", 404)
        if not current.supersedes_id:
            break
        current = db.get(Evidence, current.supersedes_id)
        if current is None:
            raise DomainError("EVIDENCE_LINEAGE_INVALID", 409)
