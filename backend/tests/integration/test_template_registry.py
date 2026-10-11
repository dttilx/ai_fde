import json
import subprocess
import sys
from copy import deepcopy

import pytest
from sqlalchemy import select

from app.access.models import User
from app.access.qualifications import qualifications
from app.diagnosis.models import ReportVersion
from app.knowledge.manual_ingest import import_manual
from app.knowledge.template_registry import (
    code_binding,
    registered_support,
    report_has_current_template_proof,
    source_binding,
    stage_template,
)
from app.shared.auth_context import ActorContext
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create

FACTS = {
    "alarm_code": "A203",
    "set_temperature_c": 165,
    "actual_temperature_c": 128,
    "heating_current_a": 0,
    "preheating_confirmed": True,
}


def test_loaded_template_fingerprint_is_stable_in_fresh_process():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from app.knowledge.template_registry import code_binding; "
            "print(json.dumps(code_binding()))",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == code_binding()


@pytest.fixture
def binding_context():
    with session_factory()() as db:
        release = import_manual(db)
        row = stage_template(db, release.id)
        assert row.status == "VERIFIED", "Explicit fixture template initialization is required"
        from app.diagnosis.models import Citation

        cites = [
            c.payload for c in db.scalars(select(Citation).where(Citation.release_id == release.id))
        ]
        yield db, row, cites
        db.rollback()


def test_explicit_fixture_binding_is_valid_and_has_no_real_approval_claim(binding_context):
    db, row, cites = binding_context
    proof = registered_support(db, FACTS, ("ELECTRICAL",), cites)
    assert proof.valid and proof.template_id == row.id
    assert row.payload["approval"]["kind"] == "SIMULATED_FIXTURE_APPROVAL"
    assert row.payload["source_bindings"] == source_binding(cites)


@pytest.mark.parametrize(
    "change",
    ["DRAFT", "RETIRED", "render_hash", "predicate_hash", "knowledge_release_key", "approval"],
)
def test_unverified_changed_or_retired_registry_never_proves_auto_release(binding_context, change):
    db, row, cites = binding_context
    if change in {"DRAFT", "RETIRED"}:
        row.status = change
    else:
        row.payload = {**row.payload, change: None if change == "approval" else "changed"}
    db.flush()
    assert not registered_support(db, FACTS, ("ELECTRICAL",), cites).valid


@pytest.mark.parametrize("change", ["locator", "excerpt", "knowledge_release_id", "checksum"])
def test_changed_citation_or_release_invalidates_binding(binding_context, change):
    db, _, cites = binding_context
    changed = deepcopy(cites)
    item = next(c for c in changed if c["source_ref"] == "H02")
    item[change] = "changed"
    assert not registered_support(db, FACTS, ("ELECTRICAL",), changed).valid


def test_old_persisted_proof_is_not_reused_after_registry_retirement():
    client, started = create(force=True)
    state = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    with session_factory()() as db:
        user = db.scalar(select(User).where(User.username == "engineer"))
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        assert "ELECTRICAL" in qualifications(db, actor)
        report = db.get(ReportVersion, state["report"]["report_version_id"])
        assert report_has_current_template_proof(db, actor, report)
        row = stage_template(db, import_manual(db).id)
        row.status = "RETIRED"
        db.flush()
        assert not report_has_current_template_proof(db, actor, report)
        db.rollback()
