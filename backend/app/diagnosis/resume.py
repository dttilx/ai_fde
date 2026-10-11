from sqlalchemy import select

from app.access.qualifications import qualifications
from app.diagnosis.budgets import charge
from app.diagnosis.models import DiagnosisRun, ReportVersion, ResumeRequest
from app.diagnosis.service import accessible_run
from app.incidents.models import Evidence, EvidenceSnapshot
from app.shared.errors import DomainError
from app.shared.jobs.service import create_job
from app.shared.versioning import content_hash


def resume_run(db, actor, run_id: str, body):
    run = accessible_run(db, actor, run_id)
    from app.access.service import require_resource

    require_resource(db, actor, "INCIDENT", run.incident_id, write=True)
    run = db.get(DiagnosisRun, run.id, with_for_update=True, populate_existing=True)
    if (
        run is None
        or run.interrupt_id != body.interrupt_id
        or run.interrupt_type != body.type
        or run.checkpoint_version != body.expected_checkpoint_version
    ):
        raise DomainError("STALE_OR_CONCURRENT_RESUME", 409)
    if run.status in {"FAILED", "COMPLETED", "ESCALATED"}:
        raise DomainError("RUN_TERMINAL", 409)
    if db.scalar(
        select(ResumeRequest).where(
            ResumeRequest.run_id == run.id, ResumeRequest.idempotency_key == body.idempotency_key
        )
    ):
        raise DomainError("DUPLICATE_SUBMISSION", 409)
    payload = {}
    from app.diagnosis.retrieval_context import require_reviewed_media, validate_media_snapshot
    from app.incidents.service import current_snapshot

    prior_snapshot = db.get(EvidenceSnapshot, run.snapshot_id)
    latest = current_snapshot(db, run.incident_id)
    if body.type in {"INFORMATION", "REPORT_REVIEW"}:
        require_reviewed_media(db, actor, run.incident_id, latest)
    evidence_changed = latest.content_hash != prior_snapshot.content_hash
    if evidence_changed:
        validate_media_snapshot(db, actor, latest)
        run.snapshot_id = latest.id
    if body.type == "REPORT_REVIEW":
        actor.require_role("FIELD_ENGINEER", "EXPERT")
        report = db.get(ReportVersion, run.report_version_id)
        if (
            report is None
            or report.id != body.report_version_id
            or report.content_hash != body.report_hash
        ):
            raise DomainError("REPORT_REVIEW_STALE", 409)
        from app.diagnosis.claim_review import accepted_reviews, required_review_qualifications
        from app.diagnosis.claim_support import conflicting_claims
        from app.knowledge.assessment_models import ClaimReview
        from app.knowledge.template_registry import report_has_current_template_proof

        if not evidence_changed and not required_review_qualifications(report.payload).issubset(
            qualifications(db, actor)
        ):
            raise DomainError("QUALIFICATION_REQUIRED", 403)

        rejected = db.scalar(
            select(ClaimReview).where(
                ClaimReview.report_id == report.id, ClaimReview.decision == "REJECT"
            )
        )
        proof_valid = report_has_current_template_proof(db, actor, report)
        if not evidence_changed and (
            rejected
            or conflicting_claims(db, report)
            or (
                (not proof_valid or report.manifest.get("human_corrected"))
                and not accepted_reviews(db, report, actor.id, body.claim_review_ids)
            )
        ):
            raise DomainError("UNRESOLVED_CLAIMS_REQUIRE_REVIEW", 409)
        payload = {
            "report_version_id": report.id,
            "report_hash": report.content_hash,
            "reviewer_id": actor.id,
            "claim_review_ids": body.claim_review_ids,
        }
        if evidence_changed:
            payload = {"evidence_changed": True}
    elif body.type == "INFORMATION":
        actor.require_role("FIELD_ENGINEER", "EXPERT")
        from app.diagnosis.questions import BOOLEAN_FIELDS, REQUIRED, RISK_FIELDS

        prior = db.get(EvidenceSnapshot, run.snapshot_id)
        allowed = set(REQUIRED.get(prior.facts.get("alarm_code"), [])) | RISK_FIELDS
        if (not body.answers and not evidence_changed) or set(body.answers) - allowed:
            raise DomainError("INFORMATION_FIELDS_INVALID")
        facts, ids = dict(prior.facts), list(prior.evidence_ids)
        for key, value in body.answers.items():
            if key in RISK_FIELDS and prior.facts.get(key) is True and value is not True:
                raise DomainError("RISK_CORRECTION_REQUIRES_EXPERT_REVIEW", 409)
            boolean = key in BOOLEAN_FIELDS | RISK_FIELDS
            if (boolean and type(value) is not bool) or (
                not boolean and type(value) not in {float, int}
            ):
                raise DomainError("INFORMATION_VALUE_INVALID")
            import math

            if isinstance(value, (float, int)) and not math.isfinite(value):
                raise DomainError("INFORMATION_VALUE_INVALID")
            if not boolean and value < 0:
                raise DomainError("INFORMATION_VALUE_INVALID")
            old = db.scalar(
                select(Evidence)
                .where(Evidence.id.in_(ids), Evidence.evidence_key == key)
                .order_by(Evidence.version.desc())
                .limit(1)
            )
            new = Evidence(
                incident_id=run.incident_id,
                evidence_key=key,
                version=old.version + 1 if old else 1,
                supersedes_id=old.id if old else None,
                state="CORRECTED" if old else "CONFIRMED",
                source="FORM",
                value={"value": value},
                reviewer_id=actor.id,
            )
            db.add(new)
            db.flush()
            if old and old.id in ids:
                ids.remove(old.id)
            ids.append(new.id)
            facts[key] = value
        unknowns = [
            item
            for item in prior.unknowns
            if not any(item.startswith(key + " ") for key in body.answers)
        ]
        snapshot = EvidenceSnapshot(
            incident_id=run.incident_id,
            evidence_ids=ids,
            facts=facts,
            unknowns=unknowns,
            contradictions=prior.contradictions,
            content_hash=content_hash([facts, ids, unknowns, prior.contradictions]),
        )
        db.add(snapshot)
        db.flush()
        run.snapshot_id = snapshot.id
        payload = {"accepted": True, "evidence_changed": evidence_changed}
    else:
        actor.require_role("EXPERT")
        if not body.resolution or not body.resolution.strip():
            raise DomainError("EXPERT_RESOLUTION_REQUIRED")
        payload = {"resolution": body.resolution.strip(), "reviewer_id": actor.id}
        if evidence_changed:
            payload["evidence_changed"] = True
    payload.update(
        resume_actor_id=actor.id, resume_actor_version=actor.auth_version, interrupt_type=body.type
    )
    charge(db, run.ledger_id, resumes=1)
    job = create_job(
        db,
        run.incident_id,
        actor.id,
        "DIAGNOSIS",
        body.idempotency_key,
        {"run_id": run.id, "resume": payload, "native_checkpoint_id": run.native_checkpoint_id},
        parent=run.active_job_id,
    )
    db.add(
        ResumeRequest(
            run_id=run.id,
            actor_id=actor.id,
            idempotency_key=body.idempotency_key,
            expected_version=body.expected_checkpoint_version,
            interrupt_id=body.interrupt_id,
            payload=body.model_dump(),
            job_id=job.id,
        )
    )
    run.interrupt_id, run.interrupt_type, run.status, run.active_job_id = (
        None,
        None,
        "PREPARING",
        job.id,
    )
    db.flush()
    from app.diagnosis.events import emit

    emit(
        db,
        run,
        "graph.resumed",
        f"resume:{job.id}",
        {
            "state": run.status,
            "checkpoint_version": run.checkpoint_version,
            "job_id": job.id,
            "thread_id": run.graph_thread_id,
        },
    )
    return run, job
