from sqlalchemy import select

from app.access.dependencies import require_action
from app.access.models import new_id
from app.access.resource_policy import authorized_source_ids
from app.diagnosis.budgets import charge
from app.diagnosis.models import DiagnosisRun, LinkedRun
from app.diagnosis.service import accessible_run
from app.shared.audit import AuditRecord
from app.shared.errors import DomainError
from app.shared.jobs.service import create_job


def create_linked_run(db, actor, parent_id, body, key):
    parent = accessible_run(db, actor, parent_id)
    require_action(db, actor, "INCIDENT", parent.incident_id, "EXPERT")
    parent = db.get(DiagnosisRun, parent.id, with_for_update=True, populate_existing=True)
    if parent.status in {"FAILED", "COMPLETED", "ESCALATED"}:
        raise DomainError("RUN_TERMINAL", 409)
    if not parent.interrupt_id:
        raise DomainError("RUN_NOT_PAUSED", 409)
    if db.scalar(
        select(LinkedRun).where(
            LinkedRun.parent_run_id == parent.id, LinkedRun.idempotency_key == key
        )
    ):
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    requested = set(body.source_scope)
    if not requested.issubset(authorized_source_ids(db, actor)):
        raise DomainError("NOT_FOUND", 404)
    if not set(parent.source_scope) < requested or not body.reason.strip():
        raise DomainError("BROADER_EXPLICIT_SCOPE_REQUIRED", 409)
    # Scope forks are continuation attempts, not a new allowance of five resumes.
    charge(db, parent.ledger_id, resumes=1)
    run_id = new_id()
    child = DiagnosisRun(
        id=run_id,
        graph_thread_id=run_id,
        incident_id=parent.incident_id,
        actor_id=actor.id,
        actor_version=actor.auth_version,
        snapshot_id=parent.snapshot_id,
        source_scope=sorted(requested),
        ledger_id=parent.ledger_id,
        force_review=True,
        asked_fields=list(parent.asked_fields),
    )
    db.add(child)
    db.flush()
    job = create_job(db, parent.incident_id, actor.id, "DIAGNOSIS", key, {"run_id": child.id})
    child.active_job_id = job.id
    db.add(
        LinkedRun(
            parent_run_id=parent.id,
            child_run_id=child.id,
            actor_id=actor.id,
            reason=body.reason.strip(),
            idempotency_key=key,
        )
    )
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="DIAGNOSIS_SCOPE_EXTENDED",
            resource_id=child.id,
            details={"parent_run_id": parent.id, "shared_ledger_id": parent.ledger_id},
        )
    )
    db.flush()
    return child, job
