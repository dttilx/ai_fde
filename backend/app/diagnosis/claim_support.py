"""Bounded citation-set judgments. Auxiliary results never approve publication."""

import time

from app.diagnosis.citation_assessment import assess_claim_sets, validate_citations
from app.diagnosis.claim_review import material_claims
from app.diagnosis.models import Citation, DiagnosisRun, ReportVersion
from app.knowledge.assessment_models import CitationAssessment, EgressReceiptRecord
from app.knowledge.assessment_policy import processing_context, profile_record
from app.knowledge.assessment_runtime import invoke
from app.shared.db import require_record, session_factory
from app.shared.errors import DomainError
from app.shared.providers.egress import authorize_egress
from app.shared.providers.jev import JevClaimJudgment
from app.shared.providers.jev_payload import build_projection, project_confirmed_facts
from app.shared.versioning import content_hash

PURPOSE = "CLAIM_SUPPORT"


async def assess_support(run_id, report_id, *, evaluator=None, guard=None):
    from app.shared.providers.jev_config import configured_evaluator

    provider = evaluator or configured_evaluator(claim=True)
    started, scheduled, result_ids = time.monotonic(), 0, []
    with session_factory()() as db:
        report = require_record(db, ReportVersion, report_id)
        claims = material_claims(report.payload)
        if not claims:
            return []
        run = require_record(db, DiagnosisRun, run_id)
        first_source = require_record(db, Citation, next(iter(claims.values()))["citation_ids"][0])
        initial = processing_context(db, run_id, first_source.source_id)
        local_results = {
            row["claim_id"]: row for row in assess_claim_sets(db, initial[1], run, report)
        }
    for claim_id, claim in claims.items():
        if guard:
            guard()
        provenance = {"attempts": 0, "reservation_ids": []}
        projection = None
        with session_factory()() as db, db.begin():
            run = require_record(db, DiagnosisRun, run_id)
            report = require_record(db, ReportVersion, report_id)
            if report.run_id != run.id or run.report_version_id != report.id:
                raise DomainError("CLAIM_REPORT_STALE", 409)
            sources = [
                require_record(db, Citation, identifier).source_id
                for identifier in claim["citation_ids"]
            ]
            contexts = [processing_context(db, run_id, identifier) for identifier in sources]
            actor, snapshot = contexts[0][1], contexts[0][3]
            if report.manifest["evidence_snapshot_hash"] != snapshot.content_hash:
                raise DomainError("CLAIM_EVIDENCE_CHANGED", 409)
            validate_citations(db, actor, report.payload["evidence_sources"])
            profile_id, profile = profile_record(db, provider.model if provider else None, provider)
            bindings = [(ctx[2].id, ctx[5], ctx[6]) for ctx in contexts]
            grants = tuple(grant for ctx in contexts for grant in ctx[4])
            current_permission = authorize_egress(grants, profile, PURPOSE, {})
            key = content_hash(
                [
                    run.id,
                    report.content_hash,
                    claim_id,
                    content_hash(claim),
                    bindings,
                    profile_id,
                    "claim-support-v1",
                    current_permission.reason,
                ]
            )
            existing = db.get(CitationAssessment, key[:36])
            if existing:
                result_ids.append(existing.id)
                continue
            local = local_results[claim_id]
            payload = {
                **local,
                "kind": "JEV_SUPPORT",
                "rubric_version": "claim-support-v1",
                "actual_model": None,
                "processing_mode": "NOT_CALLED",
                "usage_state": "NOT_CALLED",
                "support_relation": "UNKNOWN",
                "profile_id": profile_id,
                "receipt_id": None,
                "binding_hash": content_hash(bindings),
                "input_hash": None,
                "attempts": 0,
                "reservation_ids": [],
            }
            if not local["review_required"]:
                payload["reason_code"] = "INDEPENDENT_LOCAL_SUPPORT"
            else:
                # Source/incident/media DENY is checked before projecting any text.
                denied = current_permission
                if denied.reason != "JEV_PROJECTION_INVALID":
                    payload.update(status="SKIPPED_POLICY", reason_code=denied.reason)
                elif len(contexts) > 2:
                    payload.update(status="PARTIAL", reason_code="CITATION_SET_TOO_LARGE")
                elif any(
                    not ctx[2].metadata_fields.get("approved_jev_excerpt") for ctx in contexts
                ):
                    payload.update(status="SKIPPED_POLICY", reason_code="APPROVED_EXCERPT_MISSING")
                else:
                    try:
                        projection, _ = build_projection(
                            provider.model
                            if provider and provider.mode == "REAL"
                            else "jev-fixture-v1",
                            project_confirmed_facts(snapshot.facts),
                            [
                                {
                                    "source_id": ctx[2].id,
                                    "kind": ctx[2].collection,
                                    "approved_excerpt": ctx[2].metadata_fields[
                                        "approved_jev_excerpt"
                                    ],
                                }
                                for ctx in contexts
                            ],
                            ("support_relation",),
                            claim=claim.get("cause") or claim.get("text"),
                        )
                        receipt = authorize_egress(grants, profile, PURPOSE, projection)
                        receipt_record = EgressReceiptRecord(
                            run_id=run.id,
                            profile_id=profile_id,
                            payload={
                                "decision": receipt.decision,
                                "reason": receipt.reason,
                                "policy_refs": list(receipt.policy_refs),
                                "input_hash": receipt.input_hash,
                            },
                        )
                        db.add(receipt_record)
                        db.flush()
                        payload.update(
                            receipt_id=receipt_record.id,
                            input_hash=receipt.input_hash,
                            reason_code=receipt.reason,
                        )
                        if receipt.decision != "ALLOWED":
                            projection = None
                            payload["status"] = "SKIPPED_POLICY"
                    except DomainError as exc:
                        if exc.code not in {"RESIDUAL_SENSITIVE", "JEV_PROJECTION_INVALID"}:
                            raise
                        payload.update(status="SKIPPED_POLICY", reason_code=exc.code)
                        projection = None
                if projection and (provider is None or scheduled >= 4):
                    payload.update(
                        status="UNAVAILABLE" if provider is None else "SKIPPED_BUDGET",
                        reason_code="PROVIDER_NOT_CONFIGURED"
                        if provider is None
                        else "CLAIM_LIMIT",
                    )
                    projection = None
        if projection:
            scheduled += 1
            outcome, error = await invoke(
                run_id,
                sources[0],
                bindings[0][1],
                profile,
                projection,
                provider,
                provenance,
                started,
                15,
                3,
                guard,
                purpose=PURPOSE,
                related_sources=bindings,
                judgment_type=JevClaimJudgment,
            )
            payload.update(
                attempts=provenance["attempts"],
                reservation_ids=provenance["reservation_ids"],
                usage_state="UNKNOWN" if provenance.get("unknown_usage") else "KNOWN",
            )
            if outcome:
                evaluation, judgment = outcome
                payload.update(
                    status="FIXTURE" if evaluation.mode == "FIXTURE" else "SUCCESS",
                    actual_model=evaluation.actual_model,
                    processing_mode=evaluation.mode,
                    support_relation=judgment.relation,
                    reason_code=(
                        "FIXTURE_INDETERMINATE"
                        if judgment.relation == "UNKNOWN"
                        else "SCRIPTED_FIXTURE"
                    )
                    if evaluation.mode == "FIXTURE"
                    else "TYPED_MODEL_DECISION",
                )
                # Even SUPPORTS does not change local UNKNOWN into publication approval.
            else:
                payload.update(status="UNAVAILABLE", reason_code=error)
        if guard:
            guard()
        with session_factory()() as db, db.begin():
            for source_id, expected_policy, expected_scope in bindings:
                current = processing_context(db, run_id, source_id)
                if current[5] != expected_policy or current[6] != expected_scope:
                    raise DomainError("PROCESSING_PERMISSION_CHANGED", 403)
            db.add(
                CitationAssessment(id=key[:36], run_id=run_id, claim_id=claim_id, payload=payload)
            )
            db.flush()
        result_ids.append(key[:36])
    return result_ids


def conflicting_claims(db, report):
    from sqlalchemy import select

    claims = material_claims(report.payload)
    run = require_record(db, DiagnosisRun, report.run_id)
    conflicts = set()
    for row in db.scalars(
        select(CitationAssessment).where(CitationAssessment.run_id == report.run_id)
    ):
        if not (
            row.payload.get("kind") == "JEV_SUPPORT"
            and row.payload.get("report_hash") == report.content_hash
            and row.payload.get("claim_hash") == content_hash(claims.get(row.claim_id))
            and row.payload.get("support_relation") == "CONTRADICTS"
        ):
            continue
        contexts = [
            processing_context(db, run.id, require_record(db, Citation, identifier).source_id)
            for identifier in claims[row.claim_id]["citation_ids"]
        ]
        bindings = [(ctx[2].id, ctx[5], ctx[6]) for ctx in contexts]
        grants = tuple(grant for ctx in contexts for grant in ctx[4])
        from app.knowledge.assessment_policy import fixture_profile

        if (
            content_hash(bindings) == row.payload.get("binding_hash")
            and row.payload.get("evidence_snapshot_hash") == contexts[0][3].content_hash
            and authorize_egress(grants, fixture_profile(), PURPOSE, {}).reason
            == "JEV_PROJECTION_INVALID"
        ):
            conflicts.add(row.claim_id)
    return conflicts
