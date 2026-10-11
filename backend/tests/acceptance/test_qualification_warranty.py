from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.access.models import PolicyBinding, QualificationGrant, ResourceGrant, User
from app.access.qualifications import qualifications
from app.incidents.models import Asset, ServiceRestriction, WarrantyRecord
from app.shared.auth_context import ActorContext
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create, execute
from tests.acceptance.test_resource_access import fixture_client


def asset_fixture(*, confirmed=True, expired=False, restricted=False):
    asset_id = "test-apx-" + uuid4().hex
    clock = datetime.now(UTC)
    with session_factory()() as db, db.begin():
        user = db.scalar(select(User).where(User.username == "engineer"))
        assert user is not None
        db.add(
            Asset(
                id=asset_id,
                model="APX-240",
                origin="SELF_AUTHORED_SIMULATION",
                history_refs=["secret-unknown-history"],
            )
        )
        db.flush()
        db.add(ResourceGrant(user_id=user.id, resource_type="ASSET", resource_id=asset_id))
        db.add(
            PolicyBinding(
                resource_type="ASSET",
                resource_id=asset_id,
                classification="FIELD_RECORD",
                origin="SELF_AUTHORED_SIMULATION",
                readable_by=[user.id],
                egress="DENY",
            )
        )
        db.add(
            WarrantyRecord(
                asset_id=asset_id,
                status="ACTIVE",
                basis_ref="self-authored-contract:1",
                start_at=clock - timedelta(days=30),
                end_at=clock + timedelta(days=-1 if expired else 30),
                confirmed_by=user.id if confirmed else None,
                confirmed_at=clock if confirmed else None,
            )
        )
        if restricted:
            db.add(
                ServiceRestriction(
                    asset_id=asset_id,
                    term_key="wiring",
                    action_kind="CHECK_WIRING",
                    required_service_party="demo-authorized-vendor",
                    basis_ref="self-authored-contract:1#service",
                    effective_from=clock - timedelta(days=1),
                    effective_until=clock + timedelta(days=1),
                    confirmed_by=user.id,
                    confirmed_at=clock,
                )
            )
    return asset_id


@pytest.mark.parametrize(
    "confirmed,expired,status",
    [(True, False, "ACTIVE"), (True, True, "EXPIRED"), (False, False, "UNKNOWN")],
)
def test_scoped_asset_uses_confirmed_dates_not_stored_status(confirmed, expired, status):
    asset_id = asset_fixture(confirmed=confirmed, expired=expired)
    owner = fixture_client("engineer")
    response = owner.get(f"/api/assets/{asset_id}")
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["warranty"]["status"] == status
    assert summary["history_refs"] == []  # no title/identifier leak from unreadable sources
    assert summary["service_boundaries"] == []
    if not confirmed:
        assert summary["warranty"]["basis_ref"] is None
    assert fixture_client("expert").get(f"/api/assets/{asset_id}").status_code == 404
    assert owner.get("/api/assets/not-an-asset").status_code == 404


def test_unknown_warranty_does_not_block_incident_or_immediate_stop():
    asset_id = asset_fixture(confirmed=False)
    response = fixture_client("engineer").post(
        "/api/incidents",
        json={"raw_description": "A203，出现烟雾", "asset_id": asset_id},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 200, response.text
    assert response.json()["immediate_safety_notice"]["safety_blocked"] is True
    assert "SAFE-01" in response.json()["immediate_safety_notice"]["rule_ids"]


def test_effective_service_term_blocks_auto_wiring_advice_without_invented_root():
    asset_id = asset_fixture(restricted=True)
    client = fixture_client("engineer")
    summary = client.get(f"/api/assets/{asset_id}").json()
    assert summary["service_boundaries"][0]["permits_repair"] is False
    incident = client.post(
        "/api/incidents",
        json={"raw_description": "A203，设定165，实际128，加热电流0，已预热", "asset_id": asset_id},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert incident.status_code == 200
    started = client.post(
        f"/api/incidents/{incident.json()['incident_id']}/diagnoses",
        json={},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert started.status_code == 200, started.text
    execute(started.json()["job_id"])
    state = client.get(f"/api/diagnoses/{started.json()['diagnosis_run_id']}").json()
    assert state["state"] == "WAITING_EXPERT", state
    assert state["report"] is None
    assert "finalize" not in [row["node"] for row in state["timeline"]]


def test_qualification_requires_current_matching_sourced_grant_not_expert_role():
    with session_factory()() as db:
        actor = ActorContext(uuid4().hex, "apx-demo", ("EXPERT",), 1)
        db.add(
            User(
                id=actor.id,
                username="test-" + uuid4().hex,
                password_hash="not-a-login",
                roles=["EXPERT"],
            )
        )
        db.flush()
        now = datetime.now(UTC)
        for scope, basis, expiry, active in [
            ("other-model", "demo", 1, True),
            ("APX-240", "   ", 1, True),
            ("APX-240", "demo", -1, True),
            ("APX-240", "demo", 1, False),
        ]:
            db.add(
                QualificationGrant(
                    user_id=actor.id,
                    qualification="ELECTRICAL",
                    scope=scope,
                    basis=basis,
                    expires_at=now + timedelta(days=expiry),
                    active=active,
                )
            )
        db.flush()
        assert qualifications(db, actor) == ()
        db.add(
            QualificationGrant(
                user_id=actor.id,
                qualification="MECHANICAL",
                scope="APX-240",
                basis="demo:confirmed",
                expires_at=now + timedelta(days=1),
            )
        )
        db.flush()
        assert qualifications(db, actor) == ("MECHANICAL",)
        db.rollback()


def test_warranty_versions_cannot_overwrite_original():
    asset_id = asset_fixture()
    with session_factory()() as db:
        record = db.scalar(select(WarrantyRecord).where(WarrantyRecord.asset_id == asset_id))
        original_id = record.id
        record.status = "EXPIRED"
        with pytest.raises(DBAPIError):
            db.flush()
        db.rollback()
        original = db.get(WarrantyRecord, original_id)
        assert original.status == "ACTIVE"
        db.add(WarrantyRecord(asset_id=asset_id, version=2, status="UNKNOWN"))
        db.commit()
    summary = fixture_client("engineer").get(f"/api/assets/{asset_id}").json()
    assert summary["warranty"]["version"] == 2
    assert summary["warranty"]["status"] == "UNKNOWN"


def test_qualification_revocation_while_paused_blocks_resume_but_not_emergency():
    from app.diagnosis.models import DiagnosisRun, ResumeRequest

    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    state = client.get(f"/api/diagnoses/{run_id}").json()
    checkpoint = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert checkpoint["interrupt_type"] == "REPORT_REVIEW"
    with session_factory()() as db, db.begin():
        user = db.scalar(select(User).where(User.username == "engineer"))
        grants = db.scalars(
            select(QualificationGrant).where(
                QualificationGrant.user_id == user.id,
                QualificationGrant.qualification == "ELECTRICAL",
                QualificationGrant.active.is_(True),
            )
        ).all()
        assert grants
        grant_ids = [grant.id for grant in grants]
        for grant in grants:
            grant.active = False
    try:
        response = client.post(
            f"/api/diagnoses/{run_id}/resume",
            json={
                "type": "REPORT_REVIEW",
                "interrupt_id": checkpoint["interrupt_id"],
                "expected_checkpoint_version": checkpoint["checkpoint_version"],
                "idempotency_key": uuid4().hex,
                "report_version_id": state["report"]["report_version_id"],
                "report_hash": state["report_hash"],
            },
        )
        assert response.status_code == 403, response.text
        assert "QUALIFICATION_REQUIRED" in response.text
        with session_factory()() as db:
            run = db.get(DiagnosisRun, run_id)
            assert run.active_job_id == started["job_id"]
            assert run.checkpoint_version == checkpoint["checkpoint_version"]
            assert not db.scalars(select(ResumeRequest).where(ResumeRequest.run_id == run_id)).all()
        danger = client.post(
            "/api/incidents",
            json={"raw_description": "出现烟雾和焦味"},
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert danger.status_code == 200
        assert danger.json()["immediate_safety_notice"]["safety_blocked"] is True
    finally:
        with session_factory()() as db, db.begin():
            for grant_id in grant_ids:
                db.get(QualificationGrant, grant_id).active = True
