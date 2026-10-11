"""Every candidate enters this stage; only authorized projections reach a provider."""

import asyncio
import time

from app.access.models import new_id
from app.knowledge.assessment_cache import assessment_cache_key, lookup, store
from app.knowledge.assessment_models import EgressReceiptRecord, RetrievalAssessment
from app.knowledge.assessment_policy import PURPOSE, processing_context, profile_record
from app.knowledge.assessment_runtime import invoke
from app.shared.db import session_factory
from app.shared.errors import DomainError
from app.shared.providers.egress import EgressReceipt, authorize_egress
from app.shared.providers.jev import JevJudgment
from app.shared.providers.jev_payload import build_projection, project_confirmed_facts

RUBRIC = "apx-rubric-v1"
RANKING = "rrf60-preserve-v1"
HISTORY = {"HISTORICAL_CASE", "MAINTENANCE_RECORD", "APPROVED_CASE"}


def route(judgment: JevJudgment, source: dict, complete: bool) -> str:
    if judgment.instruction_signal == "TRUE" or judgment.category == "CONFLICT_REVIEW":
        return "CONFLICT_REVIEW"
    if source["pinned"] and source["collection"] not in HISTORY:
        return "REQUIRED"
    if source["collection"] in HISTORY:
        return "HISTORICAL_REFERENCE"
    if not complete or judgment.category == "UNKNOWN":
        return "UNASSESSED"
    if (
        judgment.category == "UNRELATED"
        and judgment.relevance_level == 0
        and (judgment.confidence or 0) >= 0.8
        and (judgment.probabilities or {}).get("UNRELATED", 0) >= 0.9
        and judgment.instruction_signal == "FALSE"
    ):
        return "FOLDED"
    return {
        "TECHNICAL_EVIDENCE": "EVIDENCE",
        "BACKGROUND": "BACKGROUND",
        "HISTORICAL_REFERENCE": "HISTORICAL_REFERENCE",
    }.get(judgment.category, "UNASSESSED")


def summary_status(rows: list[dict]) -> str:
    statuses = {row["status"] for row in rows}
    return (
        next(iter(statuses)) if len(statuses) == 1 else "PARTIAL" if statuses else "NO_CANDIDATES"
    )


def context_complete(facts: dict) -> bool:
    required = {
        "A203": (
            "set_temperature_c",
            "actual_temperature_c",
            "heating_current_a",
            "preheating_confirmed",
        ),
        "A310": ("upstream_pressure_mpa", "device_pressure_mpa", "continuous_leak_sound"),
        "A101": ("material_present", "p1_indicator_state"),
        "A401": ("door_closed", "door_alarm_persists_after_reclose"),
        "A520": ("visible_jam",),
        "A900": ("affected_modules", "panel_state", "onset_phase"),
    }
    fields = required.get(facts.get("alarm_code", ""), ())
    return bool(fields) and all(
        key in facts
        and facts[key] not in (None, "UNKNOWN", [])
        and not (isinstance(facts[key], list) and "UNKNOWN" in facts[key])
        for key in fields
    )


async def assess_passages(
    run_id: str,
    sources: list[dict],
    retrieval_round: int,
    guard=None,
    evaluator=None,
    limit: int = 4,
    request_seconds: float = 3,
    round_seconds: float = 15,
):
    if not 1 <= limit <= 8 or not 0 < request_seconds <= 3 or not 0 < round_seconds <= 15:
        raise DomainError("INVALID_ASSESSMENT_LIMIT")
    from app.shared.providers.jev_config import configured_evaluator

    provider = evaluator or configured_evaluator()
    with session_factory()() as db, db.begin():
        profile_id, profile = profile_record(db, provider.model if provider else None, provider)
    semaphore, round_started, scheduled = asyncio.Semaphore(2), time.monotonic(), 0

    async def one(rank, source):
        nonlocal scheduled
        started = time.monotonic()
        payload = {
            "assessment_id": new_id(),
            "source_ref": source["source_key"],
            "citation_id": f"{source['release_id']}:{source['source_key']}",
            "knowledge_release_id": source["release_id"],
            "pinned": source["pinned"],
            "hybrid_rank": rank,
            "route": route(JevJudgment(), source, False),
            "status": "SKIPPED_POLICY",
            "processing_mode": "RULE",
            "actual_model": None,
            "rubric_version": RUBRIC,
            "ranking_policy_version": RANKING,
            "relevance_level": None,
            "confidence": None,
            "probabilities": None,
            "reason_code": "INPUT_NOT_APPROVED",
            "usage_state": "NOT_CALLED",
            "latency_ms": 0,
        }
        provenance = {"retrieval_round": retrieval_round, "reservation_ids": [], "attempts": 0}
        async with semaphore:
            if guard:
                guard()
            projection, cache_key = None, None
            with session_factory()() as db, db.begin():
                run, actor, record, snapshot, grants, policy_hash, scope_hash = processing_context(
                    db, run_id, source["source_id"]
                )
                if (
                    source["release_id"] != record.release_id
                    or source["source_key"] != record.source_key
                    or source["collection"] != record.collection
                    or source.get("checksum") != record.checksum
                ):
                    raise DomainError("ASSESSMENT_SOURCE_CHANGED", 409)
                projected_facts = project_confirmed_facts(snapshot.facts)
                complete = context_complete({**snapshot.facts, **projected_facts["device_states"]})
                excerpt = record.metadata_fields.get("approved_jev_excerpt")
                if any(g.egress != "APPROVED_REDACTED" for g in grants):
                    receipt = authorize_egress(grants, profile, PURPOSE, {})
                elif not isinstance(excerpt, str) or not excerpt:
                    receipt = EgressReceipt(
                        "SKIPPED_POLICY",
                        "APPROVED_EXCERPT_MISSING",
                        "jev",
                        tuple(f"{g.policy_id}:{g.version}" for g in grants),
                    )
                else:
                    try:
                        projection, _ = build_projection(
                            provider.model
                            if provider and provider.mode == "REAL"
                            else "jev-fixture-v1",
                            projected_facts,
                            [
                                {
                                    "source_id": record.id,
                                    "kind": record.collection,
                                    "approved_excerpt": excerpt,
                                }
                            ],
                            ("relevance", "applicability", "instruction_signal"),
                        )
                        receipt = authorize_egress(grants, profile, PURPOSE, projection)
                    except DomainError as exc:
                        receipt = EgressReceipt(
                            "SKIPPED_POLICY",
                            exc.code,
                            "jev",
                            tuple(f"{g.policy_id}:{g.version}" for g in grants),
                        )
                row = EgressReceiptRecord(
                    run_id=run.id,
                    profile_id=profile_id,
                    payload={
                        "decision": receipt.decision,
                        "reason": receipt.reason,
                        "policy_refs": list(receipt.policy_refs),
                        "input_hash": receipt.input_hash,
                    },
                )
                db.add(row)
                db.flush()
                receipt_id = row.id
                provenance.update(
                    policy_hash=policy_hash,
                    scope_hash=scope_hash,
                    evidence_hash=snapshot.content_hash,
                    input_hash=receipt.input_hash,
                    context_complete=complete,
                    omitted_device_fields=[
                        key
                        for key in projected_facts["device_states"]
                        if key in snapshot.facts
                        and snapshot.facts[key] != projected_facts["device_states"][key]
                    ],
                )
                payload["reason_code"] = receipt.reason
                if receipt.decision != "ALLOWED":
                    projection = None
                elif provider is None:
                    payload.update(status="UNAVAILABLE", reason_code="PROVIDER_NOT_CONFIGURED")
                    projection = None
                else:
                    if projection is None:
                        raise DomainError("APPROVED_PROJECTION_MISSING")
                    cache_key = assessment_cache_key(
                        projection, record.checksum, RUBRIC, provider.model, policy_hash, scope_hash
                    )
                    cached = lookup(db, actor, cache_key, record.id, scope_hash)
                    if cached is not None:
                        provenance["cache_record_id"] = cached.pop("_cache_record_id")
                        payload.update(cached, status="CACHED", usage_state="NOT_CALLED")
                        provenance["cache_key"] = cache_key
                        projection = None
                    elif scheduled >= limit:
                        payload.update(status="SKIPPED_BUDGET", reason_code="ROUND_CANDIDATE_LIMIT")
                        projection = None
                    else:
                        scheduled += 1
            if projection is not None and provider is not None:
                outcome, error = await invoke(
                    run_id,
                    source["source_id"],
                    policy_hash,
                    profile,
                    projection,
                    provider,
                    provenance,
                    round_started,
                    round_seconds,
                    request_seconds,
                    guard,
                )
                if outcome is None:
                    payload.update(
                        status="SKIPPED_BUDGET" if error == "BUDGET_EXHAUSTED" else "UNAVAILABLE",
                        reason_code=error,
                        usage_state="UNKNOWN" if provenance["attempts"] else "NOT_CALLED",
                    )
                else:
                    result, judgment = outcome
                    payload.update(
                        status=("FIXTURE" if result.mode == "FIXTURE" else "SUCCESS")
                        if complete
                        else "PARTIAL",
                        processing_mode=result.mode,
                        actual_model=result.actual_model,
                        relevance_level=judgment.relevance_level,
                        confidence=judgment.confidence,
                        probabilities=judgment.probabilities,
                        route=route(judgment, source, complete),
                        reason_code=(
                            "FIXTURE_INDETERMINATE"
                            if judgment.category == "UNKNOWN"
                            else "SCRIPTED_FIXTURE_DECISION"
                        )
                        if result.mode == "FIXTURE"
                        else "TYPED_MODEL_DECISION",
                        usage_state="UNKNOWN" if provenance.get("unknown_usage") else "KNOWN",
                    )
                    provenance.update(judgment=judgment.model_dump(), projection=projection)
                    with session_factory()() as db, db.begin():
                        if cache_key is None:
                            raise DomainError("ASSESSMENT_CACHE_KEY_MISSING")
                        processing_context(db, run_id, source["source_id"])
                        store(
                            db,
                            cache_key,
                            source["source_id"],
                            scope_hash,
                            {
                                key: payload[key]
                                for key in (
                                    "processing_mode",
                                    "actual_model",
                                    "relevance_level",
                                    "confidence",
                                    "probabilities",
                                    "route",
                                    "reason_code",
                                )
                            },
                        )
            if guard:
                guard()
            payload["latency_ms"] = max(0, int((time.monotonic() - started) * 1000))
            with session_factory()() as db, db.begin():
                processing_context(db, run_id, source["source_id"])
                db.add(
                    RetrievalAssessment(
                        id=payload["assessment_id"],
                        run_id=run_id,
                        source_id=source["source_id"],
                        payload=payload,
                        provenance=provenance,
                        profile_id=profile_id,
                        receipt_id=receipt_id,
                    )
                )
            return payload

    rows = await asyncio.gather(*(one(rank, source) for rank, source in enumerate(sources, 1)))
    return {
        "diagnosis_run_id": run_id,
        "retrieval_round": retrieval_round,
        "assessments": rows,
        "status": summary_status(rows),
    }
