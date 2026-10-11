"""Committed reservations and reauthorization around every bounded provider attempt."""

import asyncio
import json
import time

from pydantic import ValidationError

from app.diagnosis.ledger import LIMITS, BudgetLedger, reserve, settle
from app.knowledge.assessment_policy import PURPOSE, processing_context
from app.shared.db import session_factory
from app.shared.errors import DomainError
from app.shared.providers.egress import authorize_egress
from app.shared.providers.jev import JevJudgment
from app.shared.providers.protocols import ProviderFailure


def reauthorize(
    db, run_id, source_id, policy_hash, profile, projection, purpose=PURPOSE, related_sources=()
):
    run, actor, record, snapshot, grants, current_policy, scope_hash = processing_context(
        db, run_id, source_id
    )
    if (
        current_policy != policy_hash
        or authorize_egress(grants, profile, purpose, projection).decision != "ALLOWED"
    ):
        raise DomainError("PROCESSING_PERMISSION_CHANGED", 403)
    for related_id, expected_policy, expected_scope in related_sources:
        context = processing_context(db, run_id, related_id)
        if (
            context[5] != expected_policy
            or context[6] != expected_scope
            or authorize_egress(context[4], profile, purpose, projection).decision != "ALLOWED"
        ):
            raise DomainError("PROCESSING_PERMISSION_CHANGED", 403)
    return run


async def invoke(
    run_id,
    source_id,
    policy_hash,
    profile,
    projection,
    evaluator,
    provenance,
    round_started,
    round_seconds,
    request_seconds,
    guard,
    *,
    purpose=PURPOSE,
    related_sources=(),
    judgment_type=JevJudgment,
):
    for attempt in range(2):
        if guard:
            guard()
        from app.access.models import new_id

        reservation_id = new_id().replace("-", "")
        try:
            with session_factory()() as db, db.begin():
                run = reauthorize(
                    db,
                    run_id,
                    source_id,
                    policy_hash,
                    profile,
                    projection,
                    purpose,
                    related_sources,
                )
                # Lock before checking headroom; two simultaneous calls cannot spend it twice.
                ledger = db.get(
                    BudgetLedger, run.ledger_id, with_for_update=True, populate_existing=True
                )
                if ledger is None:
                    raise DomainError("BUDGET_LEDGER_MISSING", 409)
                if ledger.counters.get("tools", 0) + 1 > LIMITS["tools"] - 6:
                    raise DomainError("BUDGET_EXHAUSTED", 409)
                remaining = round_seconds - (time.monotonic() - round_started)
                if remaining <= 0:
                    raise DomainError("ASSESSMENT_ROUND_TIMED_OUT", 409)
                tokens = len(json.dumps(projection, ensure_ascii=False).encode()) + 512
                reserve(db, run.ledger_id, reservation_id, {"tools": 1, "tokens": tokens})
        except DomainError as exc:
            if exc.code not in {"BUDGET_EXHAUSTED", "ASSESSMENT_ROUND_TIMED_OUT"}:
                raise
            return None, exc.code
        provenance["reservation_ids"].append(reservation_id)
        provenance["attempts"] += 1
        try:
            current_evaluator = evaluator
            if evaluator.mode == "REAL":

                def current_grants():
                    if guard:
                        guard()
                    with session_factory()() as db:
                        reauthorize(
                            db,
                            run_id,
                            source_id,
                            policy_hash,
                            profile,
                            projection,
                            purpose,
                            related_sources,
                        )
                        grants = processing_context(db, run_id, source_id)[4]
                        for related_id, _, _ in related_sources:
                            grants += processing_context(db, run_id, related_id)[4]
                        return grants

                current_evaluator = evaluator.with_permissions(current_grants)
            result = await asyncio.wait_for(
                current_evaluator.evaluate(projection), min(request_seconds, remaining)
            )
            if result.actual_model != evaluator.model or result.mode != evaluator.mode:
                raise ProviderFailure("MODEL_OR_MODE_MISMATCH")
            if result.token_usage is not None and (
                type(result.token_usage) is not int or result.token_usage < 0
            ):
                raise ProviderFailure("INVALID_USAGE")
            judgment = judgment_type.model_validate(result.judgment)
        except BaseException as exc:
            # Cancellation/crash never refunds unknown usage or hides the original failure.
            with session_factory()() as db, db.begin():
                settle(db, reservation_id, None)
            provenance["unknown_usage"] = True
            if isinstance(exc, TimeoutError):
                if attempt == 0:
                    continue
                return None, "PROVIDER_TIMEOUT"
            if isinstance(exc, ProviderFailure):
                code = str(exc)
                if code in {"RATE_LIMITED", "TEMPORARY_UNAVAILABLE"} and attempt == 0:
                    continue
                # Never expose an arbitrary provider error body through public reason_code.
                return None, code if code in {
                    "MODEL_OR_MODE_MISMATCH",
                    "INVALID_USAGE",
                    "FIXTURE_FAILURE",
                    "RATE_LIMITED",
                    "TEMPORARY_UNAVAILABLE",
                } else "PROVIDER_FAILURE"
            if isinstance(exc, ValidationError):
                return None, "PROVIDER_RESPONSE_INVALID"
            raise
        with session_factory()() as db, db.begin():
            settle(db, reservation_id, result.token_usage)
        if result.token_usage is None:
            provenance["unknown_usage"] = True
        if guard:
            guard()
        with session_factory()() as db:
            reauthorize(
                db, run_id, source_id, policy_hash, profile, projection, purpose, related_sources
            )
        return (result, judgment), None
    raise DomainError("ASSESSMENT_RETRY_STATE_INVALID")
