"""Current identity, lineage and processing permission for each assessment/cache use."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.access.models import PolicyBinding, User
from app.access.resource_policy import authorized_source_ids
from app.access.service import require_resource
from app.diagnosis.models import DiagnosisRun
from app.incidents.models import Evidence, EvidenceSnapshot
from app.incidents.service import get_incident
from app.knowledge.assessment_models import ProviderProfileRecord
from app.knowledge.models import SourceRecord
from app.shared.auth_context import ActorContext
from app.shared.db import require_record
from app.shared.errors import DomainError
from app.shared.providers.data_profile import ProcessingGrant, ProviderDataProfile
from app.shared.versioning import content_hash

PURPOSE = "PASSAGE_RELEVANCE"


def fixture_profile():
    return ProviderDataProfile(
        "jev",
        "https://api.typesafe.ai/v1/systemone",
        "fixture-profile-v1",
        "SIMULATED_LOCAL_PROCESSING_ONLY",
        datetime.now(UTC),
        True,
        ("SELF_AUTHORED_SIMULATION",),
        "LOCAL_FIXTURE_ONLY",
    )


def profile_record(db, model: str | None, provider=None):
    profile = getattr(provider, "profile", None) or fixture_profile()
    mode = "REAL" if getattr(provider, "mode", None) == "REAL" else "FIXTURE"
    payload: dict = {
        "provider": "jev",
        "version": profile.version,
        "mode": mode,
        "terms_ref": profile.terms_ref,
        "actual_model": model,
        "endpoint": "https://api.typesafe.ai/v1/systemone",
        "external_transport": mode == "REAL",
        "retention_mode": profile.retention_mode,
        "allowed_origins": list(profile.allowed_origins),
    }
    profile_id = content_hash(payload)
    db.execute(
        insert(ProviderProfileRecord)
        .values(id=profile_id, payload=payload)
        .on_conflict_do_nothing(index_elements=[ProviderProfileRecord.id])
    )
    return profile_id, profile


def processing_context(db, run_id: str, source_id: str):
    run = require_record(db, DiagnosisRun, run_id)
    user = require_record(db, User, run.actor_id)
    if not user.enabled or user.auth_version != run.actor_version:
        raise DomainError("ACTOR_REVOKED", 403)
    actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    incident = get_incident(db, actor, run.incident_id)
    require_resource(db, actor, "INCIDENT", incident.id, write=True)
    permitted = set(authorized_source_ids(db, actor))
    if source_id not in run.source_scope or not set(run.source_scope).issubset(permitted):
        raise DomainError("NOT_FOUND", 404)
    require_resource(db, actor, "SOURCE", source_id)
    source = require_record(db, SourceRecord, source_id)
    snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
    contributors = [("INCIDENT", incident.id), ("SOURCE", source.id)]
    for evidence in db.scalars(select(Evidence).where(Evidence.id.in_(snapshot.evidence_ids))):
        if evidence.source not in {"TEXT", "FORM"}:
            contributors.append(("EVIDENCE", evidence.id))
        if evidence.media_id:
            from app.evidence.policy import require_evidence_read

            require_evidence_read(db, actor, evidence)
            ancestor = evidence
            while ancestor.supersedes_id:
                ancestor = require_record(db, Evidence, ancestor.supersedes_id)
                if ("EVIDENCE", ancestor.id) not in contributors:
                    contributors.append(("EVIDENCE", ancestor.id))
            if ("MEDIA", evidence.media_id) not in contributors:
                contributors.append(("MEDIA", evidence.media_id))
    policies = []
    for kind, identifier in contributors:
        policy = db.scalar(
            select(PolicyBinding)
            .where(PolicyBinding.resource_type == kind, PolicyBinding.resource_id == identifier)
            .execution_options(populate_existing=True)
        )
        if policy is None or actor.id not in policy.readable_by:
            raise DomainError("NOT_FOUND", 404)
        policies.append(policy)
    grants = tuple(
        ProcessingGrant(
            p.id,
            p.version,
            p.origin,
            p.egress,
            tuple(p.approved_providers),
            tuple(p.approved_purposes),
            p.basis,
            p.expires_at,
            actor.id in p.readable_by,
        )
        for p in policies
    )
    policy_hash = content_hash(
        [
            {
                column.name: str(getattr(p, column.name))
                for column in PolicyBinding.__table__.columns
            }
            for p in policies
        ]
    )
    scope_hash = content_hash(
        [
            actor.id,
            actor.organization_id,
            incident.id,
            snapshot.content_hash,
            sorted(run.source_scope),
        ]
    )
    return run, actor, source, snapshot, grants, policy_hash, scope_hash
