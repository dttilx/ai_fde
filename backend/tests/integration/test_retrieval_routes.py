"""Scoped mixed retrieval over real PostgreSQL; synthetic cases are rolled back."""

from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import select

import app.incidents.models  # noqa: F401 -- register FK tables for synthetic case lineage
from app.access.models import PolicyBinding, ResourceGrant, User
from app.access.resource_policy import authorized_source_ids
from app.diagnosis.models import DiagnosisRun, ReportVersion
from app.diagnosis.retrieval_context import asset_context, citations
from app.feedback.models import CaseDraft, RepairOutcome, VerifiedCase
from app.knowledge.indexing import fixture_embedding, fuse_rankings, query_tokens
from app.knowledge.models import KnowledgeRelease, SourceRecord
from app.knowledge.retrieval import retrieve
from app.shared.auth_context import ActorContext
from app.shared.db import session_factory
from app.shared.errors import DomainError


@pytest.fixture
def context():
    with session_factory()() as db:
        user = db.scalar(select(User).where(User.username == "engineer"))
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        yield db, actor, authorized_source_ids(db, actor)


def synthetic_case(
    db, actor, *, status="VERIFIED", readable=True, key=None, publication="simulated"
):
    release = KnowledgeRelease(
        release_key=uuid4().hex, source_checksum="b" * 64, config={"mode": "FIXTURE"}
    )
    db.add(release)
    db.flush()
    text = "A203 温度偏低；自编测试案例，不是实际维修记录。"
    record = SourceRecord(
        release_id=release.id,
        source_key=key or "TEST-CASE-" + uuid4().hex,
        collection="APPROVED_CASE",
        content=text,
        locator={"page": 1, "section": "SIMULATED_FIXTURE"},
        checksum=sha256(text.encode()).hexdigest(),
        embedding=fixture_embedding(text),
        metadata_fields={
            "status": status,
            "model": "APX-240",
            "alarm_code": "A203",
            "reviewer_id": actor.id,
            "publication_id": publication,
        },
    )
    db.add(record)
    db.flush()
    if status == "VERIFIED" and publication:
        # A source metadata flag alone must never prove publication. Create a
        # fully linked synthetic published case inside this rollback-only test.
        run = db.scalar(select(DiagnosisRun).where(DiagnosisRun.actor_id == actor.id))
        report = db.scalar(select(ReportVersion).where(ReportVersion.run_id == run.id))
        outcome = RepairOutcome(
            incident_id=run.incident_id,
            diagnosis_run_id=run.id,
            report_version_id=report.id,
            submitted_by=actor.id,
            validation_status="READY_FOR_REVIEW",
            idempotency_key=uuid4().hex,
        )
        db.add(outcome)
        db.flush()
        draft = CaseDraft(repair_outcome_id=outcome.id, status="APPROVED", payload={})
        db.add(draft)
        db.flush()
        db.add(
            VerifiedCase(
                draft_id=draft.id,
                knowledge_release_id=release.id,
                status="PUBLISHED",
                approved_by=actor.id,
            )
        )
    db.add(
        PolicyBinding(
            resource_type="SOURCE",
            resource_id=record.id,
            classification="FIELD_RECORD",
            origin="SELF_AUTHORED_SIMULATION",
            readable_by=[actor.id] if readable else [],
            egress="DENY",
        )
    )
    if readable:
        db.add(ResourceGrant(user_id=actor.id, resource_type="SOURCE", resource_id=record.id))
    db.flush()
    return record


def test_exact_sources_and_logical_collections_remain_distinct(context):
    db, actor, scope = context
    rows = retrieve(db, actor, "A203", "A203 温度 电流", scope)
    by_key = {row["source_key"]: row for row in rows}
    assert {
        "SAFE-01",
        "SAFE-02",
        "SAFE-03",
        "SAFE-04",
        "SAFE-05",
        "A203",
        "H02",
        "WO-240-042",
        "MANUAL-P2",
    } <= set(by_key)
    assert by_key["A203"]["collection"] == "ALARM_CODE"
    assert by_key["H02"]["collection"] == "HISTORICAL_CASE"
    assert by_key["WO-240-042"]["collection"] == "MAINTENANCE_RECORD"
    assert all(by_key[key]["pinned"] for key in ("A203", "H02", "SAFE-01", "MANUAL-P2"))
    assert all(row["embedding_mode"] == "FIXTURE" for row in rows)
    assert len({row["release_id"] for row in rows}) == 1


@pytest.mark.parametrize(
    "status,publication",
    [("DRAFT", "simulated"), ("REJECTED", "simulated"), ("VERIFIED", None), ("VERIFIED", "")],
)
def test_unapproved_or_unpublished_cases_are_excluded_before_ranking(context, status, publication):
    db, actor, scope = context
    case = synthetic_case(db, actor, status=status, publication=publication)
    rows = retrieve(db, actor, "A203", case.content, [*scope, case.id])
    assert case.id not in {row["source_id"] for row in rows}


def test_approved_release_does_not_displace_manual_and_is_only_historical_reference(context):
    db, actor, scope = context
    case = synthetic_case(db, actor, key="A203")
    rows = retrieve(db, actor, "A203", case.content, [*scope, case.id])
    assert case.id in {row["source_id"] for row in rows}
    assert (
        next(row for row in rows if row["source_key"] == "H02")["collection"] == "HISTORICAL_CASE"
    )
    assert any(row["source_key"] == "A203" and row["collection"] == "ALARM_CODE" for row in rows)
    assert not next(row for row in rows if row["source_id"] == case.id)["pinned"]


def test_new_scope_and_revoked_grant_cannot_enter_keyword_or_vector_results(context):
    db, actor, scope = context
    hidden = synthetic_case(db, actor, readable=False)
    rows = retrieve(db, actor, "A203", hidden.content, [*scope, hidden.id])
    assert hidden.id not in {row["source_id"] for row in rows}
    assert retrieve(db, actor, "A203", "A203", []) == []
    grant = db.scalar(
        select(ResourceGrant).where(
            ResourceGrant.user_id == actor.id,
            ResourceGrant.resource_type == "SOURCE",
            ResourceGrant.resource_id == scope[0],
        )
    )
    grant.active = False
    db.flush()
    assert scope[0] not in {row["source_id"] for row in retrieve(db, actor, "A203", "A203", scope)}


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("release_id", "unbound-release"),
        ("content", "模型自行编写的引用"),
        ("locator", {"page": 999, "section": "不存在"}),
        ("collection", "APPROVED_CASE"),
        ("checksum", "0" * 64),
    ],
)
def test_forged_retrieval_content_cannot_become_a_citation(context, field, replacement):
    db, actor, scope = context
    source = deepcopy(retrieve(db, actor, "A203", "A203", scope)[0])
    source[field] = replacement
    with pytest.raises(DomainError, match="CITATION_SOURCE_CHANGED"):
        citations(db, [source])


def test_assets_are_scoped_context_without_fault_or_external_privileges(context):
    db, actor, _ = context
    summary = asset_context(db, actor, "demo-apx240-001")
    assert summary["warranty"]["status"] == "UNKNOWN"
    assert "WO-240-042" in summary["history_refs"]
    assert asset_context(db, actor, None) is None
    assert asset_context(db, actor, "demo-apx240-no-history")["history_refs"] == []
    with pytest.raises(DomainError, match="NOT_FOUND"):
        asset_context(db, actor, "unknown-qr-asset")


def test_query_identifier_dictionary_and_rrf_are_deterministic_without_semantic_claim():
    assert query_tokens("A203", "XA310X 加热 WO-240-042 H02 加热") == [
        "A203",
        "WO-240-042",
        "H02",
        "加热",
    ]
    a, b = SourceRecord(id="a"), SourceRecord(id="b")
    ranked = fuse_rankings([[a, b], [b, a]])
    assert [record.id for record, _ in ranked] == ["a", "b"]
    assert ranked[0][1] == 1 / 61 + 1 / 62
    assert fixture_embedding("A203") == fixture_embedding("A203")
    assert len(fixture_embedding("A203")) == 16
