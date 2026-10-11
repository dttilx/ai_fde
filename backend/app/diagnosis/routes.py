from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.service import require_resource
from app.diagnosis.citation_assessment import validate_citations
from app.diagnosis.ledger import BudgetLedger
from app.diagnosis.models import DiagnosisRun, NodeAudit, ReportVersion
from app.diagnosis.resume import resume_run
from app.diagnosis.schemas import CancelInput, LinkedRunInput, ResumeInput, RetryInput, StartInput
from app.diagnosis.service import accessible_run, start_run
from app.incidents.models import Incident
from app.shared.audit import AuditRecord
from app.shared.auth_context import ActorContext, current_actor
from app.shared.db import get_db, require_record
from app.shared.errors import DomainError
from app.shared.jobs.models import Job
from app.shared.jobs.service import cancel_job, retry_job

router = APIRouter(prefix="/api")


@router.get("/incidents/{incident_id}/events")
def events(incident_id: str, request: Request, last_event_id: str | None = Header(default=None)):
    import asyncio

    from fastapi.responses import StreamingResponse

    from app.diagnosis.events import authorized_events, encode_sse
    from app.shared.db import session_factory

    with session_factory()() as db:
        actor = current_actor(request, db)
        authorized_events(db, actor, incident_id, last_event_id)

    async def stream():
        cursor = last_event_id
        while not await request.is_disconnected():
            try:
                with session_factory()() as db:
                    actor = current_actor(request, db)
                    batch = authorized_events(db, actor, incident_id, cursor)
                for event in batch:
                    if await request.is_disconnected():
                        return
                    # A long batch cannot retain rights from its first event.
                    with session_factory()() as db:
                        actor = current_actor(request, db)
                        accessible_run(db, actor, event["trace_id"])
                    cursor = event["event_id"]
                    yield encode_sse(event)
                if not batch:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.5)
            except DomainError:
                # No reason/source detail is sent after access or session expiry.
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/diagnoses/{run_id}/linked-runs")
def linked_run(
    run_id: str,
    body: LinkedRunInput,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    from app.diagnosis.linked_runs import create_linked_run

    run, job = create_linked_run(db, actor, run_id, body, key)
    db.commit()
    return {
        "diagnosis_run_id": run.id,
        "graph_thread_id": run.graph_thread_id,
        "job_id": job.id,
        "state": run.status,
    }


@router.post("/incidents/{incident_id}/diagnoses")
def start(
    incident_id: str,
    body: StartInput,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    run, job = start_run(db, actor, incident_id, key, body.force_review)
    db.commit()
    return {
        "diagnosis_run_id": run.id,
        "graph_thread_id": run.graph_thread_id,
        "job_id": job.id,
        "state": run.status,
    }


@router.get("/diagnoses/{run_id}")
def get(run_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)):
    run = accessible_run(db, actor, run_id)
    report = db.get(ReportVersion, run.report_version_id) if run.report_version_id else None
    if (
        report
        and run.status in {"WAITING_EXPERT", "CONFLICT_BLOCKED", "ESCALATED"}
        and report.payload["publication_status"] != "WITHHELD"
    ):
        # Historical drafts stay immutable in storage; do not show their ordinary
        # checks as the current result after newly confirmed danger/conflicts.
        report = None
    if report:
        validate_citations(db, actor, report.payload["evidence_sources"])
    from app.diagnosis.claim_review import material_claims
    from app.knowledge.template_registry import report_has_current_template_proof
    from app.shared.versioning import content_hash

    needs_claim_review = bool(
        report
        and report.payload["publication_status"] == "DRAFT"
        and (
            report.manifest.get("human_corrected")
            or not report_has_current_template_proof(db, actor, report)
        )
    )
    audits = db.scalars(
        select(NodeAudit).where(NodeAudit.run_id == run.id).order_by(NodeAudit.created_at)
    ).all()
    from app.incidents.models import EvidenceSnapshot
    from app.safety.service import evaluate

    incident = require_record(db, Incident, run.incident_id)
    snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
    from app.diagnosis.retrieval_context import validate_media_snapshot

    validate_media_snapshot(db, actor, snapshot)
    safety = evaluate(
        incident.raw_description, snapshot.facts, contradictions=tuple(snapshot.contradictions)
    )
    return {
        "diagnosis_run_id": run.id,
        "incident_id": run.incident_id,
        "immediate_safety_notice": safety.model_dump()
        if safety.safety_blocked
        else incident.immediate_safety_notice,
        "state": run.status,
        "job_id": run.active_job_id,
        "failure_reason": run.failure_reason,
        "report": report.payload if report else None,
        "report_hash": report.content_hash if report else None,
        "manifest": report.manifest if report else None,
        "claim_review_required": needs_claim_review,
        "claim_review_items": [
            {
                "claim_id": key,
                "claim_hash": content_hash(item),
                "text": item.get("cause") or item.get("text"),
                "citation_ids": item["citation_ids"],
            }
            for key, item in material_claims(report.payload).items()
        ]
        if report and needs_claim_review
        else [],
        "timeline": [
            {
                "node": row.node_name,
                "state": row.output_status,
                "input_hash": row.input_hash,
                "details": row.details,
            }
            for row in audits
        ],
    }


@router.get("/diagnoses/{run_id}/checkpoint")
def checkpoint(
    run_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)
):
    run = accessible_run(db, actor, run_id)
    ledger = require_record(db, BudgetLedger, run.ledger_id)
    counters = ledger.counters
    from app.diagnosis.models import PendingHumanAction
    from app.diagnosis.questions import missing_fields
    from app.incidents.models import EvidenceSnapshot

    snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
    pending = db.scalar(
        select(PendingHumanAction).where(
            PendingHumanAction.run_id == run.id,
            PendingHumanAction.snapshot_hash == snapshot.content_hash,
            PendingHumanAction.kind == "INFORMATION",
        )
    )
    return {
        "diagnosis_run_id": run.id,
        "graph_thread_id": run.graph_thread_id,
        "state": run.status,
        "checkpoint_version": run.checkpoint_version,
        "resume_count": counters.get("resumes", 0),
        "interrupt_id": run.interrupt_id,
        "interrupt_type": run.interrupt_type,
        "pending_questions": missing_fields(snapshot.facts)
        if run.interrupt_type == "INFORMATION"
        else [],
        "question_details": pending.reasons
        if pending and run.interrupt_type == "INFORMATION"
        else [],
        "pending_expert_action": run.interrupt_id
        if run.interrupt_type in {"EXPERT", "HIGH_RISK"}
        else None,
        "active_job_id": run.active_job_id,
        "failure_reason": run.failure_reason,
        "counters": {
            "steps": counters.get("steps", 0),
            "retrieval_rounds": counters.get("retrievals", 0),
            "distinct_questions": counters.get("questions", 0),
            "tool_calls": counters.get("tools", 0),
            "aggregate_tokens": counters.get("tokens", 0),
            "resumes": counters.get("resumes", 0),
            "active_seconds": counters.get("active_ms", 0) / 1000,
        },
    }


@router.post("/diagnoses/{run_id}/resume")
def resume(
    run_id: str,
    body: ResumeInput,
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    run, job = resume_run(db, actor, run_id, body)
    db.commit()
    return {"diagnosis_run_id": run.id, "job_id": job.id, "state": run.status}


@router.post("/diagnoses/{run_id}/information")
def information(
    run_id: str,
    body: ResumeInput,
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    if body.type != "INFORMATION":
        raise DomainError("INTERRUPT_TYPE_MISMATCH")
    return resume(run_id, body, actor, db)


@router.post("/jobs/{job_id}/cancel")
def cancel(
    job_id: str,
    body: CancelInput,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    job = db.get(Job, job_id, with_for_update=True, populate_existing=True)
    if job is None:
        raise DomainError("NOT_FOUND", 404)
    require_resource(db, actor, "INCIDENT", job.resource_id, write=True)
    if job.kind == "DIAGNOSIS":
        accessible_run(db, actor, job.payload["run_id"])
    elif job.payload.get("media_id"):
        from app.evidence.service import accessible_media

        accessible_media(db, actor, job.payload["media_id"])
    if job.fence != body.expected_status_version or job.kind != "DIAGNOSIS":
        raise DomainError("STALE_OR_UNSUPPORTED_CANCEL", 409)
    run = db.get(DiagnosisRun, job.payload["run_id"], with_for_update=True, populate_existing=True)
    if not run or run.active_job_id != job.id or run.status in {"COMPLETED", "ESCALATED", "FAILED"}:
        raise DomainError("RUN_TERMINAL_OR_STALE", 409)
    if job.status in {"QUEUED", "RUNNING", "RETRY_WAIT"}:
        cancel_job(db, job)
    elif job.status != "SUCCEEDED" or job.result_kind != "PAUSED":
        raise DomainError("INVALID_JOB_TRANSITION", 409)
    run.status, run.failure_reason = "FAILED", "USER_CANCELLED"
    run.interrupt_id, run.interrupt_type = None, None
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="DIAGNOSIS_CANCELLED",
            resource_id=run.id,
            details={"idempotency_key": key, "job_id": job.id},
        )
    )
    db.commit()
    return {"job_id": job.id, "status": job.status, "diagnosis_state": run.status}


@router.post("/jobs/{job_id}/retry")
def retry_publication(
    job_id: str,
    body: RetryInput,
    key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100),
    actor: ActorContext = Depends(current_actor),
    db: Session = Depends(get_db),
):
    from app.feedback.models import CaseDraft
    from app.shared.versioning import content_hash

    actor.require_role("CASE_REVIEWER")
    job = db.get(Job, job_id, with_for_update=True, populate_existing=True)
    if job is None or job.kind != "CASE_PUBLICATION":
        raise DomainError("NOT_FOUND", 404)
    draft_id = job.payload["draft_id"]
    require_resource(db, actor, "CASE_DRAFT", draft_id, write=True)
    draft = db.get(CaseDraft, draft_id, with_for_update=True, populate_existing=True)
    prior = db.scalar(
        select(AuditRecord).where(
            AuditRecord.resource_id == draft_id,
            AuditRecord.action == "CASE_PUBLICATION_RETRY_REQUESTED",
            AuditRecord.details["idempotency_key"].as_string() == key,
        )
    )
    if prior:
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    if job.fence != body.expected_status_version or job.status not in {"FAILED", "TIMED_OUT"}:
        raise DomainError("STALE_OR_INVALID_RETRY", 409)
    if not draft or draft.status != "APPROVED" or draft.assigned_reviewer_id != actor.id:
        raise DomainError("CASE_PUBLICATION_NOT_APPROVED", 409)
    if draft.deidentification_status != "PASSED" or content_hash(
        [draft.payload, draft.approved_scope]
    ) != job.payload.get("approval_hash"):
        raise DomainError("CASE_PUBLICATION_APPROVAL_CHANGED", 409)
    # Reauthorize the same approved payload; never refresh a changed approval hash.
    job.actor_id = actor.id
    job.payload = {**job.payload, "actor_version": actor.auth_version}
    retry_job(db, job)
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="CASE_PUBLICATION_RETRY_REQUESTED",
            resource_id=draft_id,
            details={"idempotency_key": key, "job_id": job.id},
        )
    )
    db.commit()
    return {"job_id": job.id, "status": job.status, "status_version": job.fence}


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str, actor: ActorContext = Depends(current_actor), db: Session = Depends(get_db)
):
    job = db.get(Job, job_id)
    if job is None:
        raise DomainError("NOT_FOUND", 404)
    if job.kind == "CASE_PUBLICATION":
        require_resource(db, actor, "CASE_DRAFT", job.payload["draft_id"])
    else:
        require_resource(db, actor, "INCIDENT", job.resource_id)
    if job.kind == "DIAGNOSIS":
        accessible_run(db, actor, job.payload["run_id"])
    elif job.payload.get("media_id"):
        from app.evidence.service import accessible_media

        accessible_media(db, actor, job.payload["media_id"])
    return {
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "attempt": job.attempt,
        "deadline_at": job.deadline_at.isoformat() if job.deadline_at else None,
        "idempotency_key": job.idempotency_key,
        "error_code": job.error_code,
        "result_ref": (job.result.get("diagnosis_run_id") or job.result.get("media_id"))
        if job.result
        else None,
        "result_kind": job.result_kind,
        "parent_job_id": job.parent_job_id,
        "processing_mode": job.result.get("processing_mode", "FIXTURE")
        if job.result
        else "FIXTURE",
        "status_version": job.fence,
    }
