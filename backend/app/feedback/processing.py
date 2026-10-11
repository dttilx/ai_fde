"""Idempotent worker step for the already-reviewed case publication record."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.access.models import PolicyBinding, User
from app.access.service import require_resource
from app.feedback.models import CaseDraft, VerifiedCase
from app.knowledge.models import KnowledgeRelease, SourceRecord
from app.shared.audit import AuditRecord
from app.shared.auth_context import ActorContext
from app.shared.db import session_factory
from app.shared.invocations import assert_fence
from app.shared.jobs.executor import ExecutionResult, JobTicket
from app.shared.versioning import content_hash


async def publish_case_job(ticket: JobTicket) -> ExecutionResult:
    with session_factory()() as db, db.begin():
        assert_fence(db, ticket.job_id, ticket.fence)
        draft_id = ticket.payload["draft_id"]
        release_id = ticket.payload["release_id"]
        draft = db.get(CaseDraft, draft_id)
        release = db.get(KnowledgeRelease, release_id)
        source = db.scalar(
            select(SourceRecord).where(
                SourceRecord.release_id == release_id,
                SourceRecord.collection == "APPROVED_CASE",
            )
        )
        verified = db.scalar(select(VerifiedCase).where(VerifiedCase.draft_id == draft_id))
        if not draft or not release or not source or not verified:
            raise RuntimeError("CASE_PUBLICATION_RECORD_MISSING")
        user = db.get(User, ticket.actor_id)
        if not user or not user.enabled or "CASE_REVIEWER" not in user.roles:
            raise RuntimeError("CASE_PUBLICATION_AUTH_REVOKED")
        if user.auth_version != ticket.payload.get("actor_version"):
            raise RuntimeError("CASE_PUBLICATION_AUTH_REVOKED")
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        require_resource(db, actor, "CASE_DRAFT", draft.id, write=True)
        if content_hash([draft.payload, draft.approved_scope]) != ticket.payload.get(
            "approval_hash"
        ):
            raise RuntimeError("CASE_PUBLICATION_APPROVAL_CHANGED")
        if draft.status != "APPROVED" or draft.assigned_reviewer_id != user.id:
            raise RuntimeError("CASE_PUBLICATION_APPROVAL_REVOKED")
        if draft.deidentification_status != "PASSED":
            raise RuntimeError("CASE_PUBLICATION_DEIDENTIFICATION_REQUIRED")
        incident_policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "INCIDENT",
                PolicyBinding.resource_id == ticket.resource_id,
            )
        )
        if not incident_policy or not set(
            (draft.approved_scope or {}).get("reader_user_ids", [])
        ).issubset(incident_policy.readable_by):
            raise RuntimeError("CASE_PUBLICATION_SCOPE_REVOKED")
        if verified.status != "PUBLISHED":
            verified.status = "PUBLISHED"
            verified.published_at = datetime.now(UTC)
            db.add(
                AuditRecord(
                    actor_id=user.id,
                    actor_version=str(user.auth_version),
                    action="CASE_PUBLICATION_ACTIVATED",
                    resource_id=draft.id,
                    details={
                        "job_id": ticket.job_id,
                        "release_id": release.id,
                        "approval_hash": ticket.payload["approval_hash"],
                    },
                )
            )
    return ExecutionResult(
        "COMPLETED",
        {"draft_id": draft_id, "release_id": release_id, "status": "PUBLISHED"},
    )
