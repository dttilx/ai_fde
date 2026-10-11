"""Seven-alarm reference coverage; fixture checks do not claim live model accuracy."""

import json

from sqlalchemy import select

from app.access.models import User
from app.knowledge.passage_assessment import context_complete
from app.safety.checks import check_preconditions
from app.safety.service import evaluate
from app.shared.auth_context import ActorContext
from app.shared.config import PROJECT_ROOT
from app.shared.db import session_factory


def scenarios():
    return json.loads(
        (PROJECT_ROOT / "knowledge/seed/acceptance-scenarios.json").read_text(encoding="utf-8")
    )


def test_all_exam_alarms_have_page_four_source_records():
    rows = json.loads(
        (PROJECT_ROOT / "knowledge/seed/alarm-codes.json").read_text(encoding="utf-8")
    )
    assert {row["id"] for row in rows} == {"A101", "A203", "A205", "A310", "A401", "A520", "A900"}
    assert all(row["source_page"] == 4 and row["source_section"] == "3. 报警码说明" for row in rows)
    assert all(row["source_checksum"] and row["egress"] == "DENY" for row in rows)


def test_complete_and_incomplete_contexts_are_explicit():
    for row in scenarios():
        if row["expected"] in {"COVERED", "REVIEW"}:
            complete = context_complete({"alarm_code": row["alarm_code"], **row["facts"]})
            if row["alarm_code"] != "A205":
                assert complete, row["id"]
        elif row["expected"] == "INCOMPLETE":
            assert not context_complete(
                {"alarm_code": row["alarm_code"], **row["facts"]}
            ), row["id"]


def test_a205_alarm_alone_is_immediate_safety_block():
    decision = evaluate("A205", {"alarm_code": "A205"})
    assert decision.safety_blocked and decision.escalate_expert
    assert "A205" in decision.rule_ids and decision.citations


def test_preconditions_keep_alarm_and_safety_citations_and_never_allow_operation():
    with session_factory()() as db:
        actor_user = db.scalar(select(User).where(User.username == "engineer"))
        assert actor_user is not None
        actor = ActorContext(
            actor_user.id,
            actor_user.organization_id,
            tuple(actor_user.roles),
            actor_user.auth_version,
        )
        # Use an existing incident owned by the fixture engineer.
        from app.incidents.models import Incident

        incident = db.scalar(
            select(Incident)
            .where(Incident.owner_id == actor.id)
            .order_by(Incident.created_at.desc())
        )
        assert incident is not None
        result = check_preconditions(db, actor, incident.id, "CHECK_HEATER")
        assert result["allows_device_operation"] is False
        assert {item["source_ref"] for item in result["citations"]}.issuperset(
            {"SAFE-02", "SAFE-03", "SAFE-04"}
        )
