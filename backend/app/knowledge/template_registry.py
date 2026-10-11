"""Version-bound local template governance; model output never approves a template."""

import hashlib
import inspect
from datetime import UTC, datetime
from types import CodeType

from sqlalchemy import select

from app.access.models import User
from app.access.qualifications import qualifications
from app.access.resource_policy import authorized_source_ids
from app.diagnosis.normalization import PATTERNS, normalize, unconfirmed_context
from app.diagnosis.report import LABELS, UNITS, a203_draft, format_fact
from app.knowledge.models import KnowledgeRelease, SourceRecord
from app.knowledge.template_models import TemplateRegistry
from app.knowledge.templates import TemplateSupport, a203_support, a310_support
from app.shared.audit import AuditRecord
from app.shared.auth_context import ActorContext
from app.shared.config import settings
from app.shared.errors import DomainError
from app.shared.versioning import content_hash

KEYS = {"A203", "H02", "WO-240-042", "MANUAL-P2", *[f"SAFE-0{i}" for i in range(1, 6)]}


def required_source_keys(alarm):
    return (
        KEYS
        if alarm == "A203"
        else {"A310", "H03", "WO-240-051", "MANUAL-P2", *[f"SAFE-0{i}" for i in range(1, 6)]}
    )


def required_qualification(alarm):
    return "MECHANICAL" if alarm == "A310" else "ELECTRICAL"


def code_binding(alarm="A203") -> dict:
    renderer, predicate = a203_draft, a203_support
    if alarm == "A310":
        from app.diagnosis.pressure_report import a310_draft

        renderer, predicate = a310_draft, a310_support

    def normalize_constant(value):
        if isinstance(value, CodeType):
            return normalize_code(value)
        if isinstance(value, tuple):
            return [normalize_constant(v) for v in value]
        if isinstance(value, frozenset):
            return sorted([normalize_constant(v) for v in value], key=repr)
        if isinstance(value, bytes):
            return {"bytes": value.hex()}
        return value

    def normalize_code(code):
        return {
            "code": code.co_code.hex(),
            "consts": [normalize_constant(v) for v in code.co_consts],
            "names": code.co_names,
            "locals": code.co_varnames,
            "free": code.co_freevars,
            "cells": code.co_cellvars,
            "args": [code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount],
            "flags": code.co_flags,
            "exception_table": code.co_exceptiontable.hex(),
        }

    def fingerprint(function):
        # Bind both source and loaded code: a stale worker must not attest to a newer disk file.
        return content_hash(
            [
                inspect.getsource(function),
                normalize_code(function.__code__),
                normalize_constant(function.__defaults__),
            ]
        )

    return {
        "render_hash": content_hash(
            [fingerprint(renderer), fingerprint(format_fact), LABELS, UNITS]
        ),
        "predicate_hash": fingerprint(predicate),
        "normalization_hash": content_hash(
            [fingerprint(normalize), fingerprint(unconfirmed_context), PATTERNS]
        ),
        "contract": "report-v4",
    }


def source_binding(citations: list[dict], alarm="A203") -> dict:
    return {
        row["source_ref"]: {
            "citation_id": row["citation_id"],
            "checksum": row["checksum"],
            "locator": row["locator"],
            "collection": row["source_type"],
        }
        for row in citations
        if row["source_ref"] in required_source_keys(alarm)
    }


def stage_template(db, release_id: str, alarm="A203") -> TemplateRegistry:
    from app.diagnosis.retrieval_context import citations

    release = db.get(KnowledgeRelease, release_id)
    if not release:
        raise DomainError("KNOWLEDGE_RELEASE_MISSING", 409)
    records = db.scalars(
        select(SourceRecord).where(
            SourceRecord.release_id == release_id,
            SourceRecord.source_key.in_(required_source_keys(alarm)),
        )
    ).all()
    if {r.source_key for r in records} != required_source_keys(alarm):
        raise DomainError("TEMPLATE_SOURCES_INCOMPLETE", 409)
    cites = citations(
        db,
        [
            {
                "source_id": r.id,
                "checksum": r.checksum,
                "release_id": r.release_id,
                "content": r.content,
                "locator": r.locator,
                "collection": r.collection,
            }
            for r in records
        ],
    )
    payload = {
        **code_binding(alarm),
        "source_bindings": source_binding(cites, alarm),
        "alarm_code": alarm,
        "knowledge_release_key": release.release_key,
        "fixture_only": True,
        "validation_suite_ref": "tests/unit/test_template_support.py",
        "approval": None,
    }
    template_id = f"{alarm}-FIXTURE:{release_id}:{content_hash(payload)[:16]}"
    row = db.get(TemplateRegistry, template_id)
    if row is None:
        row = TemplateRegistry(
            id=template_id, release_id=release_id, version="v1", status="DRAFT", payload=payload
        )
        db.add(row)
        db.flush()
    return row


def simulate_fixture_approval(db, row: TemplateRegistry, username: str) -> None:
    if settings().provider_mode != "FIXTURE":
        raise DomainError("FIXTURE_APPROVAL_FORBIDDEN", 403)
    user = db.scalar(select(User).where(User.username == username, User.enabled.is_(True)))
    if not user:
        raise DomainError("TEMPLATE_REVIEWER_MISSING", 403)
    actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
    actor.require_role("EXPERT")
    alarm = row.payload.get("alarm_code", "A203")
    if required_qualification(alarm) not in qualifications(db, actor):
        raise DomainError("QUALIFICATION_REQUIRED", 403)
    needed = db.scalars(
        select(SourceRecord.id).where(
            SourceRecord.release_id == row.release_id,
            SourceRecord.source_key.in_(required_source_keys(alarm)),
        )
    ).all()
    if not set(needed).issubset(authorized_source_ids(db, actor)):
        raise DomainError("TEMPLATE_SOURCES_NOT_ACCESSIBLE", 403)
    if row.status == "VERIFIED":
        return
    if row.status != "DRAFT":
        raise DomainError("TEMPLATE_NOT_DRAFT", 409)
    row.payload = {
        **row.payload,
        "approval": {
            "kind": "SIMULATED_FIXTURE_APPROVAL",
            "actor_id": actor.id,
            "actor_version": actor.auth_version,
            "at": datetime.now(UTC).isoformat(),
        },
    }
    row.status = "VERIFIED"
    db.add(
        AuditRecord(
            actor_id=actor.id,
            actor_version=str(actor.auth_version),
            action="SIMULATED_FIXTURE_TEMPLATE_APPROVAL",
            resource_id=row.id,
            details={"binding_hash": content_hash(row.payload), "fixture_only": True},
        )
    )


def registered_support(db, facts, qualified, cites, contradictions=()) -> TemplateSupport:
    alarm = facts.get("alarm_code", "A203")
    predicate = a310_support if alarm == "A310" else a203_support
    base = predicate(facts, qualified, {c["source_ref"] for c in cites}, contradictions)
    if not base.valid:
        return base
    releases = {c["knowledge_release_id"] for c in cites}
    if len(releases) != 1:
        return TemplateSupport(False, base.template_id, ("MIXED_KNOWLEDGE_RELEASES",))
    if any(hashlib.sha256(c["excerpt"].encode()).hexdigest() != c["checksum"] for c in cites):
        return TemplateSupport(False, base.template_id, ("SOURCE_CONTENT_CHANGED",))
    release_id = next(iter(releases))
    release = db.get(KnowledgeRelease, release_id)
    rows = db.scalars(
        select(TemplateRegistry)
        .where(TemplateRegistry.release_id == release_id, TemplateRegistry.status == "VERIFIED")
        .with_for_update()
    ).all()
    for row in rows:
        payload = row.payload
        if (
            settings().provider_mode == "FIXTURE"
            and payload.get("fixture_only") is True
            and (payload.get("approval") or {}).get("kind") == "SIMULATED_FIXTURE_APPROVAL"
            and release
            and payload.get("knowledge_release_key") == release.release_key
            and payload.get("alarm_code") == alarm
            and all(payload.get(k) == v for k, v in code_binding(alarm).items())
            and set(source_binding(cites, alarm)) == required_source_keys(alarm)
            and payload.get("source_bindings") == source_binding(cites, alarm)
        ):
            return TemplateSupport(True, row.id, ())
    return TemplateSupport(False, base.template_id, ("TEMPLATE_UNVERIFIED_OR_BINDING_CHANGED",))


def report_has_current_template_proof(db, actor, report) -> bool:
    from app.diagnosis.citation_assessment import validate_citations
    from app.diagnosis.release_models import ValidationProof
    from app.incidents.models import EvidenceSnapshot

    proof = db.scalar(
        select(ValidationProof).where(ValidationProof.report_hash == report.content_hash)
    )
    if not proof or proof.payload.get("mode") != "RULE" or report.manifest.get("human_corrected"):
        return False
    snapshot = db.scalar(
        select(EvidenceSnapshot).where(EvidenceSnapshot.content_hash == proof.evidence_hash)
    )
    row = db.get(TemplateRegistry, proof.template_id)
    if (
        not snapshot
        or not row
        or content_hash(row.payload) != proof.payload.get("template_binding_hash")
    ):
        return False
    validate_citations(db, actor, report.payload["evidence_sources"])
    support = registered_support(
        db,
        snapshot.facts,
        qualifications(db, actor),
        report.payload["evidence_sources"],
        tuple(snapshot.contradictions),
    )
    return support.valid and support.template_id == proof.template_id
