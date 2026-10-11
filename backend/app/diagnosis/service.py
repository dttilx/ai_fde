import asyncio
from typing import Literal

from langgraph.types import Command

from app.access.dependencies import require_action
from app.access.models import User, new_id
from app.access.resource_policy import authorized_source_ids
from app.diagnosis.checkpoints import checkpoint_store
from app.diagnosis.graph import build_graph
from app.diagnosis.ledger import BudgetLedger
from app.diagnosis.models import DiagnosisRun
from app.diagnosis.nodes import DiagnosisNodes
from app.incidents.service import current_snapshot, get_incident
from app.shared.db import session_factory
from app.shared.errors import DomainError
from app.shared.invocations import assert_fence
from app.shared.jobs.executor import ExecutionResult
from app.shared.jobs.service import create_job


def start_run(db, actor, incident_id: str, key: str, force_review: bool):
    incident = get_incident(db, actor, incident_id)
    require_action(db, actor, "INCIDENT", incident_id, "FIELD_ENGINEER", "EXPERT")
    snapshot = current_snapshot(db, incident.id)
    from app.diagnosis.retrieval_context import require_reviewed_media

    require_reviewed_media(db, actor, incident.id, snapshot)
    run_id, ledger_id = new_id(), new_id()
    db.add(BudgetLedger(id=ledger_id, counters={}))
    db.flush()
    run = DiagnosisRun(
        id=run_id,
        graph_thread_id=run_id,
        incident_id=incident.id,
        actor_id=actor.id,
        actor_version=actor.auth_version,
        snapshot_id=snapshot.id,
        source_scope=authorized_source_ids(db, actor),
        ledger_id=ledger_id,
        force_review=force_review,
    )
    db.add(run)
    db.flush()
    job = create_job(db, incident.id, actor.id, "DIAGNOSIS", key, {"run_id": run.id})
    run.active_job_id = job.id
    db.flush()
    return run, job


def accessible_run(db, actor, run_id: str):
    run = db.get(DiagnosisRun, run_id)
    if run is None:
        raise DomainError("NOT_FOUND", 404)
    get_incident(db, actor, run.incident_id)
    from app.diagnosis.retrieval_context import validate_media_snapshot
    from app.incidents.models import EvidenceSnapshot
    from app.shared.db import require_record

    validate_media_snapshot(db, actor, require_record(db, EvidenceSnapshot, run.snapshot_id))
    if not set(run.source_scope).issubset(authorized_source_ids(db, actor)):
        raise DomainError("NOT_FOUND", 404)
    return run


def execute_sync(ticket) -> ExecutionResult:
    nodes = DiagnosisNodes(ticket)
    run_id = ticket.payload["run_id"]
    try:
        with checkpoint_store() as store:
            graph = build_graph(store, nodes.handlers())
            config = {"configurable": {"thread_id": run_id}, "recursion_limit": 32}
            if "resume" in ticket.payload:
                resumed = ticket.payload["resume"]
                with session_factory()() as db:
                    reviewer = db.get(User, resumed.get("resume_actor_id"))
                    allowed_roles = (
                        {"EXPERT"}
                        if resumed.get("interrupt_type") in {"EXPERT", "HIGH_RISK"}
                        else {"FIELD_ENGINEER", "EXPERT"}
                    )
                    if (
                        not reviewer
                        or not reviewer.enabled
                        or reviewer.auth_version != resumed.get("resume_actor_version")
                        or not allowed_roles.intersection(reviewer.roles)
                    ):
                        raise DomainError("RESUME_ACTOR_REVOKED", 403)
                previous = graph.get_state(config)
                if (
                    previous.config["configurable"].get("checkpoint_id")
                    != ticket.payload["native_checkpoint_id"]
                ):
                    raise DomainError("CHECKPOINT_VERSION_MISMATCH", 409)
                # Native interrupts replay their node. Run the independent named safety node first,
                # before any resumed finalize/retrieval logic; waiting does not consume active time.
                refreshed = nodes.safety_gate(previous.values)
                expert_acknowledgement = (
                    previous.next == ("expert_review",)
                    and resumed.get("interrupt_type") in {"EXPERT", "HIGH_RISK"}
                    and previous.values.get("evidence_snapshot_hash")
                    == refreshed["evidence_snapshot_hash"]
                )
                if (
                    refreshed["safety"]["safety_blocked"]
                    and not expert_acknowledgement
                    or resumed.get("evidence_changed")
                ):
                    graph.update_state(config, refreshed, as_node="prepare")
                    graph.invoke(None, config)
                else:
                    graph.invoke(Command(resume=ticket.payload["resume"]), config)
            else:
                graph.invoke({"diagnosis_run_id": run_id}, config)
            snapshot = graph.get_state(config)
            interrupts = [item for task in snapshot.tasks for item in task.interrupts]
            with session_factory()() as db, db.begin():
                assert_fence(db, ticket.job_id, ticket.fence)
                run = db.get(DiagnosisRun, run_id, with_for_update=True)
                if run is None or run.active_job_id != ticket.job_id:
                    raise DomainError("RUN_FENCED", 409)
                nodes.account_active(db, run)
                run.native_checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
                run.checkpoint_version += 1
                run.interrupt_id = interrupts[0].id if interrupts else None
                run.interrupt_type = interrupts[0].value["type"] if interrupts else None
                if not interrupts:
                    run.status = snapshot.values["status"]
                result_kind: Literal["PAUSED", "COMPLETED"] = (
                    "PAUSED" if interrupts else "COMPLETED"
                )
                from app.diagnosis.events import emit

                emit(
                    db,
                    run,
                    "graph.interrupted"
                    if interrupts
                    else (
                        "diagnosis.report_ready"
                        if run.status == "COMPLETED" and run.report_version_id
                        else "graph.completed"
                    ),
                    f"checkpoint:{run.id}:{run.checkpoint_version}",
                    {
                        "state": run.status,
                        "checkpoint_version": run.checkpoint_version,
                        "interrupt_type": run.interrupt_type,
                        "job_id": ticket.job_id,
                    },
                )
                return ExecutionResult(
                    result_kind,
                    {
                        "diagnosis_run_id": run.id,
                        "checkpoint_version": run.checkpoint_version,
                        "native_checkpoint_id": run.native_checkpoint_id,
                    },
                )
    except Exception as exc:
        code = exc.code if isinstance(exc, DomainError) else "GRAPH_EXECUTION_FAILED"
        with session_factory()() as db, db.begin():
            run = db.get(DiagnosisRun, run_id, with_for_update=True)
            if (
                run
                and run.active_job_id == ticket.job_id
                and run.failure_reason != "USER_CANCELLED"
            ):
                run.status, run.failure_reason = "FAILED", code
        raise DomainError(code, 409) from None


async def execute_diagnosis(ticket) -> ExecutionResult:
    return await asyncio.to_thread(execute_sync, ticket)
