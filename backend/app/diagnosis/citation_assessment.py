import hashlib

from sqlalchemy.orm import Session

from app.access.resource_policy import authorized_source_ids
from app.diagnosis.models import Citation
from app.knowledge.models import SourceRecord
from app.shared.auth_context import ActorContext
from app.shared.errors import DomainError
from app.shared.versioning import content_hash


def validate_citations(db: Session, actor: ActorContext, citation_payloads: list[dict]) -> None:
    permitted = set(authorized_source_ids(db, actor))
    for item in citation_payloads:
        citation = db.get(Citation, item["citation_id"])
        if not citation or citation.source_id not in permitted:
            raise DomainError("CITATION_NOT_ACCESSIBLE", 404)
        source = db.get(SourceRecord, citation.source_id)
        if (
            source is None
            or item != citation.payload
            or source.release_id != item["knowledge_release_id"]
            or source.source_key != item["source_ref"]
            or source.collection != item["source_type"]
            or f"第{source.locator['page']}页 / {source.locator['section']}" != item["locator"]
            or source.checksum != item["checksum"]
            or hashlib.sha256(item["excerpt"].encode()).hexdigest() != source.checksum
        ):
            raise DomainError("CITATION_PROVENANCE_INVALID", 409)


def assess_claim_sets(db, actor, run, report) -> list[dict]:
    """Existence is checked before support. No entailment is inferred from relevance."""
    from sqlalchemy import select

    from app.access.models import PolicyBinding, User
    from app.access.qualifications import qualifications
    from app.diagnosis.claim_review import (
        material_claims,
        required_review_qualifications,
        review_binding,
    )
    from app.diagnosis.models import ReportVersion
    from app.incidents.models import EvidenceSnapshot
    from app.knowledge.assessment_models import ClaimReview
    from app.knowledge.template_registry import report_has_current_template_proof
    from app.shared.auth_context import ActorContext
    from app.shared.db import require_record

    validate_citations(db, actor, report.payload["evidence_sources"])
    snapshot = require_record(db, EvidenceSnapshot, run.snapshot_id)
    evidence_current = (
        snapshot.content_hash == report.manifest["evidence_snapshot_hash"]
        and not snapshot.contradictions
    )
    rule_valid = evidence_current and report_has_current_template_proof(db, actor, report)
    review_target = report
    if report.payload["release_mode"] == "HUMAN_REVIEWED" and report.parent_id:
        review_target = require_record(db, ReportVersion, report.parent_id)
    reviews = db.scalars(select(ClaimReview).where(ClaimReview.report_id == review_target.id)).all()
    approved: set[str] = set()
    rejected = {row.claim_id for row in reviews if row.decision == "REJECT"}
    target_claims = material_claims(review_target.payload)
    for reviewer_id in {row.actor_id for row in reviews}:
        user = db.get(User, reviewer_id)
        if not user or not user.enabled or not evidence_current:
            continue
        reviewer = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        if not set(reviewer.roles).intersection({"FIELD_ENGINEER", "EXPERT"}) or (
            not required_review_qualifications(review_target.payload).issubset(
                qualifications(db, reviewer)
            )
        ):
            continue
        try:
            binding = review_binding(db, reviewer, run, review_target)
        except DomainError as exc:
            if exc.status in {403, 404} or exc.code == "REPORT_REVIEW_EVIDENCE_CHANGED":
                continue
            raise
        published_ids = report.payload.get("claim_review_ids", [])
        for row in reviews:
            claim = target_claims.get(row.claim_id)
            if (
                row.actor_id == reviewer_id
                and row.decision == "ACCEPT"
                and row.claim_id not in rejected
                and claim
                and row.report_hash == review_target.content_hash
                and row.claim_hash == content_hash(claim)
                and row.payload.get("binding") == binding
                and (report.payload["publication_status"] != "PUBLISHED" or row.id in published_ids)
            ):
                approved.add(row.claim_id)
    by_id = {cite["citation_id"]: cite for cite in report.payload["evidence_sources"]}
    result = []
    for claim_id, claim in material_claims(report.payload).items():
        citations = [by_id[citation_id] for citation_id in claim["citation_ids"]]
        source_ids = [db.get(Citation, cite["citation_id"]).source_id for cite in citations]
        policies = db.scalars(
            select(PolicyBinding).where(
                (
                    (PolicyBinding.resource_type == "SOURCE")
                    & PolicyBinding.resource_id.in_(source_ids)
                )
                | (
                    (PolicyBinding.resource_type == "INCIDENT")
                    & (PolicyBinding.resource_id == run.incident_id)
                )
            )
        ).all()
        denied = len(policies) != len(set(source_ids)) + 1 or any(
            p.egress == "DENY" for p in policies
        )
        supported = (
            evidence_current and claim_id not in rejected and (rule_valid or claim_id in approved)
        )
        result.append(
            {
                "report_version_id": report.id,
                "report_hash": report.content_hash,
                "claim_id": claim_id,
                "claim_hash": content_hash(claim),
                "citation_ids": claim["citation_ids"],
                "relation": "SUPPORTED" if supported else "UNKNOWN",
                "mode": "RULE"
                if supported and rule_valid
                else "HUMAN"
                if supported
                else "NOT_CALLED",
                "status": "VERIFIED"
                if supported
                else "REJECTED"
                if claim_id in rejected
                else "SKIPPED_POLICY"
                if denied
                else "NOT_RUN",
                "review_required": not supported,
                "evidence_snapshot_hash": snapshot.content_hash,
                "scope": "ADVISORY_ONLY_NOT_CONFIRMED_ROOT",
                "historical_reference_ids": [
                    c["citation_id"]
                    for c in citations
                    if c["source_type"]
                    in {"HISTORICAL_CASE", "MAINTENANCE_RECORD", "APPROVED_CASE"}
                ],
            }
        )
    from app.knowledge.assessment_models import CitationAssessment
    from app.knowledge.assessment_policy import fixture_profile, processing_context
    from app.shared.providers.egress import authorize_egress

    auxiliary = db.scalars(
        select(CitationAssessment).where(CitationAssessment.run_id == run.id)
    ).all()
    context_cache = {}
    for item in result:
        candidates = [
            row.payload
            for row in auxiliary
            if row.payload.get("kind") == "JEV_SUPPORT"
            and row.claim_id == item["claim_id"]
            and row.payload.get("report_hash") == review_target.content_hash
            and row.payload.get("claim_hash") == item["claim_hash"]
            and row.payload.get("evidence_snapshot_hash") == snapshot.content_hash
        ]
        if not candidates:
            continue
        auxiliary_binding = []
        current_grants = []
        for identifier in item["citation_ids"]:
            source_id = require_record(db, Citation, identifier).source_id
            if source_id not in context_cache:
                try:
                    context_cache[source_id] = processing_context(db, run.id, source_id)
                except DomainError as exc:
                    if exc.status not in {403, 404}:
                        raise
                    context_cache[source_id] = None
            context = context_cache[source_id]
            if context is not None:
                auxiliary_binding.append((source_id, context[5], context[6]))
                current_grants.extend(context[4])
        permitted_now = (
            authorize_egress(tuple(current_grants), fixture_profile(), "CLAIM_SUPPORT", {}).reason
            == "JEV_PROJECTION_INVALID"
        )
        matches = [
            entry
            for entry in candidates
            if len(auxiliary_binding) == len(item["citation_ids"])
            and entry.get("binding_hash") == content_hash(auxiliary_binding)
            and (entry.get("actual_model") is None or permitted_now)
        ]
        if matches:
            entry = matches[-1]
            item.update(
                auxiliary_support_relation=entry["support_relation"],
                jev_status=entry["status"],
                actual_model=entry["actual_model"],
                processing_mode=entry["processing_mode"],
            )
            if entry["support_relation"] == "CONTRADICTS":
                item.update(relation="UNKNOWN", review_required=True, status="CONFLICT_REVIEW")
    return result


def record_claim_sets(db, actor, run, report) -> list[str]:
    from sqlalchemy import select

    from app.knowledge.assessment_models import CitationAssessment

    records = db.scalars(
        select(CitationAssessment).where(CitationAssessment.run_id == run.id)
    ).all()
    existing = {content_hash(row.payload): row.id for row in records}
    ids = []
    for payload in assess_claim_sets(db, actor, run, report):
        key = content_hash(payload)
        if key in existing:
            ids.append(existing[key])
            continue
        row = CitationAssessment(run_id=run.id, claim_id=payload["claim_id"], payload=payload)
        db.add(row)
        db.flush()
        ids.append(row.id)
    return ids
