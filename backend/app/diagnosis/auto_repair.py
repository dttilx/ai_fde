"""One automatic withdrawal of an unsupported cause; never invent a replacement root."""

from copy import deepcopy

from sqlalchemy import select

from app.access.models import new_id
from app.diagnosis.claim_review import material_claims
from app.diagnosis.ledger import CallReservation, reserve, settle
from app.diagnosis.models import Citation, DiagnosisRun, ReportVersion
from app.diagnosis.release_models import ReportReleaseDecision
from app.diagnosis.report import validate_report
from app.knowledge.assessment_models import CitationAssessment
from app.knowledge.assessment_policy import processing_context, profile_record
from app.shared.audit import AuditRecord
from app.shared.db import require_record, session_factory
from app.shared.errors import DomainError
from app.shared.providers.egress import authorize_egress
from app.shared.versioning import content_hash


def repair_once(run_id, report_id, assessment_ids, *, guard=None):
    if guard:
        guard()
    with session_factory()() as db, db.begin():
        run = db.get(DiagnosisRun, run_id, with_for_update=True, populate_existing=True)
        report = require_record(db, ReportVersion, report_id)
        if not run or run.report_version_id != report.id or report.run_id != run.id:
            raise DomainError("CLAIM_REPORT_STALE", 409)
        claims = material_claims(report.payload)
        assessments = db.scalars(
            select(CitationAssessment).where(
                CitationAssessment.id.in_(assessment_ids), CitationAssessment.run_id == run.id
            )
        ).all()
        unsupported = {
            row.claim_id
            for row in assessments
            if row.payload.get("kind") == "JEV_SUPPORT"
            and row.payload.get("report_hash") == report.content_hash
            and row.payload.get("claim_hash") == content_hash(claims.get(row.claim_id))
            and row.payload.get("support_relation") == "UNSUPPORTED"
        }
        causes = [
            item for item in report.payload["possible_causes"] if item["claim_id"] in unsupported
        ]
        for row in assessments:
            if row.claim_id not in unsupported:
                continue
            contexts = [
                processing_context(db, run_id, require_record(db, Citation, identifier).source_id)
                for identifier in claims[row.claim_id]["citation_ids"]
            ]
            binding = [(ctx[2].id, ctx[5], ctx[6]) for ctx in contexts]
            _, profile = profile_record(db, row.payload.get("actual_model"))
            grants = tuple(grant for ctx in contexts for grant in ctx[4])
            if (
                content_hash(binding) != row.payload.get("binding_hash")
                or authorize_egress(grants, profile, "CLAIM_SUPPORT", {}).reason
                != "JEV_PROJECTION_INVALID"
            ):
                raise DomainError("PROCESSING_PERMISSION_CHANGED", 403)
        key = f"auto-repair:{run.ledger_id}"
        existing_reservation = db.get(CallReservation, key)
        if not causes or existing_reservation is not None:
            return None
        reserve(db, run.ledger_id, key, {"tools": 1, "steps": 1})
        settle(db, key, 0)
        changed = deepcopy(report.payload)
        for item in changed["possible_causes"]:
            if item["claim_id"] in unsupported:
                item["cause"] = "当前引用不足以支持此候选原因，无法判断，需人工核实。"
        changed.update(
            report_version_id=new_id(),
            release_decision_id=new_id(),
            validation_check_ids=[],
            claim_review_ids=[],
            reviewer_ids=[],
            release_mode="PENDING_REVIEW",
            publication_status="DRAFT",
            status="FINALIZING",
        )
        validate_report(changed)
        changed_hash = content_hash(changed)
        db.add(
            ReportVersion(
                id=changed["report_version_id"],
                run_id=run.id,
                parent_id=report.id,
                payload=changed,
                content_hash=changed_hash,
                manifest={
                    **report.manifest,
                    "human_corrected": True,
                    "automatic_repair_attempts": 1,
                    "automatic_repair_kind": "WITHDRAW_UNSUPPORTED_CAUSE",
                    "repair_assessment_ids": assessment_ids,
                    "correction_parent_hash": report.content_hash,
                },
            )
        )
        db.add(
            ReportReleaseDecision(
                id=changed["release_decision_id"],
                report_hash=changed_hash,
                mode="PENDING_REVIEW",
                payload={"automatic_repair_from": report.id},
            )
        )
        db.add(
            AuditRecord(
                actor_id=run.actor_id,
                actor_version=str(run.actor_version),
                action="AUTO_CLAIM_REPAIR",
                resource_id=run.id,
                details={
                    "old_hash": report.content_hash,
                    "new_hash": changed_hash,
                    "reservation_id": key,
                    "claim_ids": sorted(unsupported),
                },
            )
        )
        run.report_version_id = changed["report_version_id"]
        db.flush()
        return changed["report_version_id"]
