import asyncio
import time

from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import User, new_id
from app.access.qualifications import qualification_records, qualifications
from app.access.resource_policy import authorized_source_ids
from app.diagnosis.budgets import charge, require_available
from app.diagnosis.citation_assessment import record_claim_sets, validate_citations
from app.diagnosis.graph import GRAPH_VERSION
from app.diagnosis.models import DiagnosisRun, NodeAudit, ReportVersion
from app.diagnosis.questions import REQUIRED, missing_fields, persist_questions, question_details
from app.diagnosis.release_models import ReportReleaseDecision, ValidationProof
from app.diagnosis.release_policy import release_mode
from app.diagnosis.report import a203_draft, validate_report
from app.diagnosis.retrieval_context import asset_context, citations
from app.incidents.models import Evidence, EvidenceSnapshot, Incident
from app.knowledge.assessment_models import RetrievalAssessment
from app.knowledge.passage_assessment import assess_passages
from app.knowledge.retrieval import retrieve
from app.knowledge.template_models import TemplateRegistry
from app.knowledge.template_registry import (
    registered_support,
    required_qualification,
    required_source_keys,
)
from app.safety.schemas import rule_citations
from app.safety.service import evaluate
from app.shared.audit import AuditRecord
from app.shared.auth_context import ActorContext
from app.shared.db import require_record, session_factory
from app.shared.errors import DomainError
from app.shared.invocations import assert_fence
from app.shared.versioning import content_hash

REQUIRED_A203 = [
    "set_temperature_c",
    "preheating_confirmed",
    "actual_temperature_c",
    "heating_current_a",
]


class DiagnosisNodes:
    def __init__(self, ticket):
        self.ticket = ticket
        self.run_id = ticket.payload["run_id"]
        self.accounted_at = time.monotonic()

    def account_active(self, db: Session, run: DiagnosisRun):
        observed = time.monotonic()
        elapsed_ms = max(0, int((observed - self.accounted_at) * 1000))
        charge(db, run.ledger_id, active_ms=elapsed_ms)
        self.accounted_at = observed

    def context(
        self, db: Session, node_name: str, count_step: bool = True
    ) -> tuple[DiagnosisRun, ActorContext]:
        assert_fence(db, self.ticket.job_id, self.ticket.fence)
        run = db.get(DiagnosisRun, self.run_id, with_for_update=True)
        if (
            run is None
            or run.active_job_id != self.ticket.job_id
            or run.status in {"FAILED", "COMPLETED", "ESCALATED"}
        ):
            raise DomainError("RUN_NOT_ACTIVE", 409)
        user = db.get(User, run.actor_id)
        if not user or not user.enabled or user.auth_version != run.actor_version:
            raise DomainError("ACTOR_REVOKED", 403)
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        from app.access.service import require_resource

        actor.require_role("FIELD_ENGINEER", "EXPERT")
        require_resource(db, actor, "INCIDENT", run.incident_id, write=True)
        from app.diagnosis.retrieval_context import validate_media_snapshot

        validate_media_snapshot(db, actor, require_record(db, EvidenceSnapshot, run.snapshot_id))
        from app.diagnosis.retrieval_context import validate_media_snapshot

        validate_media_snapshot(db, actor, require_record(db, EvidenceSnapshot, run.snapshot_id))
        if not set(run.source_scope).issubset(authorized_source_ids(db, actor)):
            raise DomainError("SOURCE_SCOPE_REVOKED", 403)
        require_available(db, run.ledger_id)
        self.account_active(db, run)
        if count_step:
            charge(db, run.ledger_id, steps=1)
        return run, actor

    def audit(self, db: Session, run: DiagnosisRun, node: str, status: str, tools=(), cites=()):
        snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
        ledger = require_available(db, run.ledger_id)
        from app.diagnosis.events import emit
        from app.knowledge.models import SourceRecord

        releases = sorted(
            set(
                db.scalars(
                    select(SourceRecord.release_id).where(SourceRecord.id.in_(run.source_scope))
                )
            )
        )
        audit = NodeAudit(
            run_id=run.id,
            node_name=node,
            input_hash=snapshot.content_hash,
            output_status=status,
            details={
                "tools": list(tools),
                "counters": ledger.counters,
                "citation_ids": list(cites),
                "graph_version": GRAPH_VERSION,
                "prompt_version": "fixture-reference-v1",
                "model_version": "fixture/rule-only",
                "evidence_snapshot_id": snapshot.id,
                "knowledge_release_ids": releases,
                "checkpoint_version": run.checkpoint_version,
                "job_id": self.ticket.job_id,
                "job_fence": self.ticket.fence,
            },
        )
        db.add(audit)
        db.flush()
        emit(
            db,
            run,
            "graph.node_completed",
            f"node:{audit.id}",
            {
                "node_name": node,
                "output_state": status,
                "evidence_snapshot_hash": snapshot.content_hash,
                "counters": dict(ledger.counters),
                "citation_ids": list(cites),
                "graph_version": GRAPH_VERSION,
                "checkpoint_version": run.checkpoint_version,
                "job_id": self.ticket.job_id,
            },
        )

    def prepare(self, state):
        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "prepare")
            incident = require_record(db, Incident, run.incident_id)
            snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
            result = {
                "diagnosis_run_id": run.id,
                "raw_text": incident.raw_description,
                "facts": snapshot.facts,
                "qualifications": qualifications(db, actor),
                "evidence_snapshot_hash": snapshot.content_hash,
                "status": "PREPARING",
                "needed_information": False,
            }
            self.audit(db, run, "prepare", "PREPARING")
            return result

    def safety_gate(self, state):
        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "safety_gate")
            snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
            incident = require_record(db, Incident, run.incident_id)
            decision = evaluate(
                incident.raw_description,
                snapshot.facts,
                qualifications(db, actor),
                contradictions=tuple(snapshot.contradictions),
            )
            result = decision.model_dump()
            if not decision.safety_blocked:
                result = self.service_gate(db, actor, incident, snapshot.facts, result)
            run.status = "SAFETY_CHECK"
            self.audit(db, run, "safety_gate", "SAFETY_CHECK")
            return {
                "status": "SAFETY_CHECK",
                "evidence_snapshot_hash": snapshot.content_hash,
                "facts": snapshot.facts,
                "qualifications": qualifications(db, actor),
                "safety": result,
            }

    def service_gate(self, db, actor, incident, facts, safety):
        if facts.get("alarm_code") not in {"A203", "A310"}:
            return safety
        from app.safety.checks import check_preconditions

        action = "PRESSURE_WORK" if facts.get("alarm_code") == "A310" else "CHECK_WIRING"
        check = check_preconditions(db, actor, incident.id, action)
        restrictions = check["service_restrictions"]
        if not check["safety_blocked"]:
            return safety
        return {
            **safety,
            "status": "RISK_UNKNOWN",
            "safety_blocked": True,
            "escalate_expert": True,
            "rule_ids": ["SAFE-04"],
            "citations": rule_citations(["SAFE-04"]),
            "reasons": check["qualification_reasons"]
            + [
                "服务条款要求由 "
                f"{term['required_service_party']} 处理 {action}；"
                f"需人工核实服务方授权，依据 {term['basis_ref']}。"
                for term in restrictions
            ],
        }

    def retrieve(self, state):
        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "retrieve")
            charge(db, run.ledger_id, retrievals=1, tools=1)
            if state["safety"]["safety_blocked"]:
                raise DomainError("SAFETY_BLOCKS_RETRIEVAL", 409)
            incident = require_record(db, Incident, run.incident_id)
            # Asset route stays distinct from fault citations and cannot widen source scope.
            from app.diagnosis.retrieval_context import snapshot_asset_id

            snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
            asset_context(db, actor, snapshot_asset_id(db, incident, snapshot))
            sources = retrieve(
                db, actor, state["facts"].get("alarm_code", ""), state["raw_text"], run.source_scope
            )
            # Keep the report's template proof bound to one manual release. Reviewed
            # cases may still be retrieved and assessed, but a later case release
            # cannot silently turn the exam-grounded report into mixed provenance.
            primary_release = next(
                (source["release_id"] for source in sources if source["pinned"]), None
            )
            report_sources = [
                source
                for source in sources
                if primary_release is None or source["release_id"] == primary_release
            ]
            citation_payloads = citations(db, report_sources)
            ledger = require_available(db, run.ledger_id)
            retrieval_round = ledger.counters["retrievals"]
            run_id = run.id

        # Commit node/call budgets before invoking a provider, and release row locks.
        def guard():
            with session_factory()() as db, db.begin():
                self.context(db, "retrieve", count_step=False)

        assessment = asyncio.run(assess_passages(run_id, sources, retrieval_round, guard=guard))
        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "retrieve", count_step=False)
            assessment_rows = db.scalars(
                select(RetrievalAssessment).where(
                    RetrievalAssessment.id.in_(
                        [row["assessment_id"] for row in assessment["assessments"]]
                    )
                )
            ).all()
            attempts = sum(row.provenance.get("attempts", 0) for row in assessment_rows)
            covered = state["facts"].get("alarm_code") in {
                source["source_key"] for source in sources
            }
            support = evaluate(
                state["raw_text"],
                state["facts"],
                state["qualifications"],
                coverage=covered,
                contradictions=("检索来源存在冲突或异常指令信号，须人工核实",)
                if any(row["route"] == "CONFLICT_REVIEW" for row in assessment["assessments"])
                else (),
            )
            run.status = "RETRIEVING"
            self.audit(
                db,
                run,
                "retrieve",
                "RETRIEVING",
                ("hybrid_retrieval", *("jev_assessment" for _ in range(attempts))),
                [c["citation_id"] for c in citation_payloads],
            )
            return {
                "status": "RETRIEVING",
                "retrieved": sources,
                "safety": support.model_dump(),
                "citation_payloads": citation_payloads,
                "assessment": assessment,
            }

    def decide(self, state):
        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "decide")
            missing = missing_fields(state["facts"])
            if state["safety"]["safety_blocked"]:
                status = "WAITING_EXPERT"
            elif state["facts"].get("alarm_code") not in REQUIRED:
                # Other alarm-specific reports are separate tasks, not invented by this slice.
                state = {
                    **state,
                    "safety": {
                        **state["safety"],
                        "safety_blocked": True,
                        "reasons": ["本实现切片尚未提供该报警的诊断报告，请交专家处理。"],
                    },
                }
                status = "WAITING_EXPERT"
            elif not required_source_keys(state["facts"].get("alarm_code")).issubset(
                {row["source_ref"] for row in state.get("citation_payloads", [])}
            ):
                state = {**state, "safety": evaluate("", {}, coverage=False).model_dump()}
                status = "WAITING_EXPERT"
            elif missing:
                status = "NEEDS_INFORMATION"
            elif (
                required_qualification(state["facts"].get("alarm_code"))
                not in state["qualifications"]
            ):
                decision = evaluate(
                    "",
                    {},
                    requested_actions=(
                        "检查线路" if state["facts"].get("alarm_code") == "A203" else "气路拆装",
                    ),
                )
                state = {**state, "safety": decision.model_dump()}
                status = "WAITING_EXPERT"
            else:
                status = "FINALIZING"
            run.status = status
            self.audit(db, run, "decide", status)
            return {
                "status": status,
                "needed_information": bool(missing),
                "missing_fields": missing,
                "safety": state["safety"],
            }

    def ask_information(self, state):
        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "ask_information")
            newly_asked = set(state["missing_fields"]) - set(run.asked_fields)
            charge(db, run.ledger_id, questions=len(newly_asked))
            run.asked_fields = sorted(set(run.asked_fields).union(newly_asked))
            # interrupt() replays this node; keep the original questions bound to
            # their pre-answer snapshot rather than recording an empty/new question set.
            snapshot = db.scalar(
                select(EvidenceSnapshot).where(
                    EvidenceSnapshot.incident_id == run.incident_id,
                    EvidenceSnapshot.content_hash == state["evidence_snapshot_hash"],
                )
            )
            if snapshot is None:
                raise DomainError("QUESTION_SNAPSHOT_MISSING", 409)
            details = question_details(state["facts"], state["citation_payloads"])
            persist_questions(db, run, snapshot, details)
            run.status = "NEEDS_INFORMATION"
            self.audit(db, run, "ask_information", "NEEDS_INFORMATION")
        interrupt(
            {"type": "INFORMATION", "missing_fields": state["missing_fields"], "questions": details}
        )
        # Submitted facts were validated and persisted before enqueuing this resume Job.
        with session_factory()() as db:
            run = require_record(db, DiagnosisRun, self.run_id)
            snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
            return {"facts": snapshot.facts, "needed_information": False}

    def expert_review(self, state):
        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "expert_review")
            run.status = (
                "CONFLICT_BLOCKED"
                if state["safety"]["status"] == "CONFLICT_BLOCKED"
                else "WAITING_EXPERT"
            )
            snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
            from app.diagnosis.human_actions import ensure_expert_action

            ensure_expert_action(db, run, snapshot, state["safety"]["reasons"])
            self.audit(db, run, "expert_review", run.status)
        answer = interrupt({"type": "EXPERT", "safety": state["safety"]})
        return {"expert_disposition": answer, "status": "ESCALATED"}

    def finalize(self, state):
        if state.get("safety", {}).get("safety_blocked"):
            with session_factory()() as db, db.begin():
                run, actor = self.context(db, "finalize")
                self.audit(db, run, "finalize", "ESCALATED")
            return {"status": "ESCALATED"}
        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "finalize")
            snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
            incident = require_record(db, Incident, run.incident_id)
            if self.service_gate(db, actor, incident, snapshot.facts, state["safety"])[
                "safety_blocked"
            ]:
                raise DomainError("SERVICE_AUTHORIZATION_REQUIRED", 403)
            cite_payloads = state["citation_payloads"]
            validate_citations(db, actor, cite_payloads)
            proof = registered_support(
                db,
                snapshot.facts,
                qualifications(db, actor),
                cite_payloads,
                tuple(snapshot.contradictions),
            )
            existing_draft = (
                db.get(ReportVersion, run.report_version_id) if run.report_version_id else None
            )
            parent_draft = existing_draft
            if (
                existing_draft is not None
                and existing_draft.manifest["evidence_snapshot_hash"] != snapshot.content_hash
            ):
                existing_draft = None
            if existing_draft is None:
                mode = release_mode(
                    proof,
                    safety_clear=True,
                    force_review=run.force_review,
                    has_blocking_questions=False,
                    contradictions=bool(snapshot.contradictions),
                    access_valid=True,
                )
                version_id, decision_id, check_id = new_id(), new_id(), new_id()
                evidence = [
                    {
                        "id": row.id,
                        "key": row.evidence_key,
                        "value": row.value["value"],
                        "state": row.state,
                        "media_id": row.media_id,
                        "source": row.source,
                        "locators": row.locators,
                    }
                    for row in db.scalars(
                        select(Evidence).where(Evidence.id.in_(snapshot.evidence_ids))
                    )
                    if row.evidence_key != "asset_association"
                ]
                grants = qualification_records(db, actor)
                policy_refs = [
                    {
                        "policy_reference_id": grant.id,
                        "kind": "QUALIFICATION",
                        "version": "1",
                        "basis_ref": grant.basis,
                    }
                    for grant in grants
                ]
                renderer = a203_draft
                if snapshot.facts.get("alarm_code") == "A310":
                    from app.diagnosis.pressure_report import a310_draft

                    renderer = a310_draft
                payload = renderer(
                    run.id,
                    version_id,
                    snapshot.facts,
                    evidence,
                    cite_payloads,
                    snapshot.unknowns,
                    policy_refs,
                    "PENDING_REVIEW",
                    decision_id,
                    [check_id] if proof.valid else [],
                )
                report_hash = content_hash(payload)
                self.account_active(db, run)
                assert_fence(db, self.ticket.job_id, self.ticket.fence)
                assessment_ids = [
                    row["assessment_id"]
                    for row in state.get("assessment", {}).get("assessments", [])
                ]
                assessment_records = db.scalars(
                    select(RetrievalAssessment).where(RetrievalAssessment.id.in_(assessment_ids))
                ).all()
                jev_models = sorted(
                    {
                        row.payload["actual_model"]
                        for row in assessment_records
                        if row.payload["actual_model"]
                    }
                )
                manifest = {
                    "intended_release_mode": mode,
                    "graph_version": GRAPH_VERSION,
                    "prompt_version": "fixture-reference-v1",
                    "model_versions": {
                        "generator": "RULE/FIXTURE",
                        "embedding": "fixture-hash16-v1",
                        "jev": ",".join(jev_models) if jev_models else "NO_MODEL_RESULT",
                    },
                    "knowledge_release_id": cite_payloads[0]["knowledge_release_id"],
                    "evidence_snapshot_hash": snapshot.content_hash,
                    "citation_ids": [c["citation_id"] for c in cite_payloads],
                    "source_scope_hash": content_hash(run.source_scope),
                    "ledger_id": run.ledger_id,
                    "access_version": str(actor.auth_version),
                    "egress_version": "PER_CONTRIBUTOR_RECEIPTS",
                    "assessment_refs": [
                        {
                            "assessment_id": row.id,
                            "profile_id": row.profile_id,
                            "receipt_id": row.receipt_id,
                            "policy_hash": row.provenance.get("policy_hash"),
                            "scope_hash": row.provenance.get("scope_hash"),
                            "input_hash": row.provenance.get("input_hash"),
                            "reservation_ids": row.provenance.get("reservation_ids", []),
                        }
                        for row in assessment_records
                    ],
                }
                report = ReportVersion(
                    id=version_id,
                    run_id=run.id,
                    parent_id=parent_draft.id if parent_draft else None,
                    payload=payload,
                    manifest=manifest,
                    content_hash=report_hash,
                )
                db.add(report)
                db.add(
                    ReportReleaseDecision(
                        id=decision_id,
                        report_hash=report_hash,
                        mode="PENDING_REVIEW",
                        payload={
                            "snapshot_hash": snapshot.content_hash,
                            "template": proof.template_id,
                            "failed_predicates": list(proof.failed_predicates),
                        },
                    )
                )
                if proof.valid:
                    db.add(
                        ValidationProof(
                            id=check_id,
                            report_hash=report_hash,
                            evidence_hash=snapshot.content_hash,
                            template_id=proof.template_id,
                            payload={
                                "mode": "RULE",
                                "fixture_only": True,
                                "template_binding_hash": content_hash(
                                    require_record(db, TemplateRegistry, proof.template_id).payload
                                ),
                                "source_refs": [c["citation_id"] for c in cite_payloads],
                            },
                        )
                    )
                run.report_version_id = version_id
                db.flush()
            else:
                report = existing_draft
                mode = report.manifest.get("intended_release_mode", report.payload["release_mode"])
                if report.manifest.get("human_corrected"):
                    mode = "PENDING_REVIEW"
                if report.manifest["evidence_snapshot_hash"] != snapshot.content_hash:
                    raise DomainError("REPORT_REVIEW_EVIDENCE_CHANGED", 409)
            self.audit(
                db, run, "finalize", "FINALIZING", cites=[c["citation_id"] for c in cite_payloads]
            )
            record_claim_sets(db, actor, run, report)
            draft_id, draft_hash = report.id, report.content_hash
        from app.diagnosis.auto_repair import repair_once
        from app.diagnosis.claim_support import assess_support

        def support_guard():
            with session_factory()() as db, db.begin():
                self.context(db, "finalize", count_step=False)

        support_ids = asyncio.run(assess_support(self.run_id, draft_id, guard=support_guard))
        from app.diagnosis.claim_support import conflicting_claims

        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "finalize", count_step=False)
            draft = require_record(db, ReportVersion, draft_id)
            if conflicting_claims(db, draft):
                from app.diagnosis.withholding import withhold_conflict

                withhold_conflict(db, run, draft, support_ids)
                blocked = evaluate(
                    "", {}, contradictions=("引用与候选结论冲突，须专家核实引用和陈述。",)
                ).model_dump()
                run.status = "CONFLICT_BLOCKED"
                self.audit(db, run, "finalize", "CONFLICT_BLOCKED", tools=("jev_claim_support",))
                return {"status": "CONFLICT_BLOCKED", "safety": blocked}
        repaired = repair_once(self.run_id, draft_id, support_ids, guard=support_guard)
        if repaired:
            draft_id = repaired
            with session_factory()() as db:
                draft = require_record(db, ReportVersion, draft_id)
                draft_hash, mode = draft.content_hash, "PENDING_REVIEW"
        if mode == "AUTO_VALIDATED":
            self.publish_auto(draft_id, support_ids)
        if mode == "PENDING_REVIEW":
            review = interrupt(
                {"type": "REPORT_REVIEW", "report_version_id": draft_id, "report_hash": draft_hash}
            )
            if (
                review.get("report_version_id") != draft_id
                or review.get("report_hash") != draft_hash
            ):
                raise DomainError("REPORT_REVIEW_STALE", 409)
            with session_factory()() as db, db.begin():
                run, actor = self.context(db, "finalize")
                snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
                draft = require_record(db, ReportVersion, draft_id)
                from app.diagnosis.claim_review import accepted_reviews
                from app.knowledge.template_registry import report_has_current_template_proof

                if (
                    not report_has_current_template_proof(db, actor, draft)
                    or draft.manifest.get("human_corrected")
                ) and not accepted_reviews(
                    db, draft, review["reviewer_id"], review.get("claim_review_ids", [])
                ):
                    raise DomainError("UNRESOLVED_CLAIMS_REQUIRE_REVIEW", 409)
                validate_citations(db, actor, draft.payload["evidence_sources"])
                payload = dict(draft.payload)
                payload.update(
                    report_version_id=new_id(),
                    status="COMPLETED",
                    publication_status="PUBLISHED",
                    release_mode="HUMAN_REVIEWED",
                    reviewer_ids=[review["reviewer_id"]],
                    release_decision_id=new_id(),
                    claim_review_ids=review.get("claim_review_ids", []),
                    validation_check_ids=[new_id()],
                )
                validate_report(payload)
                new_hash = content_hash(payload)
                self.account_active(db, run)
                assert_fence(db, self.ticket.job_id, self.ticket.fence)
                db.add(
                    ValidationProof(
                        id=payload["validation_check_ids"][0],
                        report_hash=new_hash,
                        evidence_hash=snapshot.content_hash,
                        template_id=proof.template_id
                        if proof.valid and not draft.manifest.get("human_corrected")
                        else "HUMAN-CITED-CLAIMS-v1",
                        payload={
                            "mode": "HUMAN_REVIEWED",
                            "reviewed_draft_hash": draft_hash,
                            "claim_review_ids": review.get("claim_review_ids", []),
                            "source_refs": [
                                c["citation_id"] for c in draft.payload["evidence_sources"]
                            ],
                        },
                    )
                )
                db.add(
                    ReportVersion(
                        id=payload["report_version_id"],
                        run_id=run.id,
                        parent_id=draft.id,
                        payload=payload,
                        content_hash=new_hash,
                        manifest={
                            **draft.manifest,
                            "reviewed_draft_hash": draft_hash,
                            "review_execution_graph_version": GRAPH_VERSION,
                            "claim_support_assessment_ids": support_ids,
                        },
                    )
                )
                db.add(
                    ReportReleaseDecision(
                        id=payload["release_decision_id"],
                        report_hash=new_hash,
                        mode="HUMAN_REVIEWED",
                        payload={"reviewed_hash": draft_hash, "reviewer_id": review["reviewer_id"]},
                    )
                )
                db.add(
                    AuditRecord(
                        actor_id=review["reviewer_id"],
                        actor_version=str(actor.auth_version),
                        action="REPORT_REVIEWED",
                        resource_id=run.id,
                        details={"reviewed_hash": draft_hash},
                    )
                )
                run.report_version_id = payload["report_version_id"]
                db.flush()
                record_claim_sets(
                    db, actor, run, require_record(db, ReportVersion, run.report_version_id)
                )
        return {"status": "COMPLETED"}

    def publish_auto(self, draft_id, support_ids):
        """Publish only after support checks and final invocation/budget guards."""
        from app.diagnosis.claim_support import conflicting_claims
        from app.knowledge.template_registry import report_has_current_template_proof

        with session_factory()() as db, db.begin():
            run, actor = self.context(db, "finalize", count_step=False)
            draft = require_record(db, ReportVersion, draft_id)
            if draft.payload["publication_status"] == "PUBLISHED":
                return
            if (
                run.report_version_id != draft.id
                or conflicting_claims(db, draft)
                or not report_has_current_template_proof(db, actor, draft)
            ):
                raise DomainError("AUTO_RELEASE_NOT_VALID", 409)
            payload = {
                **draft.payload,
                "report_version_id": new_id(),
                "release_decision_id": new_id(),
                "validation_check_ids": [new_id()],
                "release_mode": "AUTO_VALIDATED",
                "publication_status": "PUBLISHED",
                "status": "COMPLETED",
            }
            validate_report(payload)
            report_hash = content_hash(payload)
            proof = require_record(db, ValidationProof, draft.payload["validation_check_ids"][0])
            db.add(
                ValidationProof(
                    id=payload["validation_check_ids"][0],
                    report_hash=report_hash,
                    evidence_hash=proof.evidence_hash,
                    template_id=proof.template_id,
                    payload={**proof.payload, "reviewed_draft_hash": draft.content_hash},
                )
            )
            db.add(
                ReportVersion(
                    id=payload["report_version_id"],
                    run_id=run.id,
                    parent_id=draft.id,
                    payload=payload,
                    content_hash=report_hash,
                    manifest={
                        **draft.manifest,
                        "claim_support_assessment_ids": support_ids,
                        "validated_draft_hash": draft.content_hash,
                    },
                )
            )
            db.add(
                ReportReleaseDecision(
                    id=payload["release_decision_id"],
                    report_hash=report_hash,
                    mode="AUTO_VALIDATED",
                    payload={"validated_draft_hash": draft.content_hash},
                )
            )
            self.account_active(db, run)
            assert_fence(db, self.ticket.job_id, self.ticket.fence)
            run.report_version_id = payload["report_version_id"]
            db.flush()
            record_claim_sets(
                db, actor, run, require_record(db, ReportVersion, run.report_version_id)
            )

    def handlers(self):
        return {
            name: getattr(self, name)
            for name in (
                "prepare",
                "safety_gate",
                "retrieve",
                "decide",
                "ask_information",
                "expert_review",
                "finalize",
            )
        }
