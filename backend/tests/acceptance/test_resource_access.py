import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant, User
from app.access.qualifications import qualifications
from app.access.resource_policy import authorized_source_ids
from app.access.service import require_resource
from app.access.session import hasher
from app.main import app
from app.shared.auth_context import ActorContext
from app.shared.config import PROJECT_ROOT, settings
from app.shared.providers.data_profile import ProcessingGrant, ProviderDataProfile
from app.shared.providers.egress import authorize_egress


def fixture_client(name):
    credentials = json.loads((PROJECT_ROOT / ".private/demo-credentials.json").read_text())
    client = TestClient(app)
    auth = client.post(
        "/api/session", json={"username": name, "password": credentials[name]["password"]}
    )
    assert auth.status_code == 200
    client.headers.update({"X-CSRF-Token": auth.json()["csrf_token"]})
    return client


def test_incident_scope_spoofing_and_immediate_safety():
    engineer, expert, reviewer = [
        fixture_client(name) for name in ("engineer", "expert", "reviewer")
    ]
    headers = {"Idempotency-Key": uuid4().hex}
    body = {"raw_description": "现场出现焦味", "alarm_code": "A203"}
    created = engineer.post("/api/incidents", json=body, headers=headers)
    assert created.status_code == 200
    incident_id = created.json()["incident_id"]
    assert created.json()["immediate_safety_notice"]["safety_blocked"]
    assert engineer.get(f"/api/incidents/{incident_id}").status_code == 200
    assert expert.get(f"/api/incidents/{incident_id}").status_code == 404
    assert reviewer.get(f"/api/incidents/{incident_id}").status_code == 404
    assert engineer.post("/api/incidents", json=body, headers=headers).status_code == 409
    assert (
        reviewer.post(
            "/api/incidents", json=body, headers={"Idempotency-Key": uuid4().hex}
        ).status_code
        == 403
    )
    assert (
        engineer.post(
            "/api/incidents",
            json={**body, "actor_id": "expert"},
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 422
    )


def test_a203_text_normalization_and_asset_boundary():
    client = fixture_client("engineer")
    created = client.post(
        "/api/incidents",
        json={
            "raw_description": "A203，设定165，实际128，加热电流0，已预热",
            "asset_id": "demo-apx240-001",
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 200
    assert created.json()["facts"]["heating_current_a"] == 0
    assert created.json()["facts"]["preheating_confirmed"] is True
    assert created.json()["immediate_safety_notice"] is None
    other = client.post(
        "/api/incidents",
        json={"raw_description": "A203", "asset_id": "demo-other-001"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert other.status_code == 422


def new_scoped_client(roles):
    """Separate server-issued identity, not an override of authentication dependencies."""
    admin = create_engine(settings().migration_database_url.get_secret_value())
    name = "scope-" + uuid4().hex
    with Session(admin) as db, db.begin():
        user = User(username=name, password_hash=hasher.hash("scope-fixture"), roles=roles)
        db.add(user)
        db.flush()
        user_id = user.id
    client = TestClient(app)
    response = client.post("/api/session", json={"username": name, "password": "scope-fixture"})
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": response.json()["csrf_token"]})
    return client, user_id, admin


def grant_incident(admin, incident_id, user_id, permission):
    with Session(admin) as db, db.begin():
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "INCIDENT", PolicyBinding.resource_id == incident_id
            )
        )
        policy.readable_by = [*policy.readable_by, user_id]
        db.add(
            ResourceGrant(
                user_id=user_id,
                resource_type="INCIDENT",
                resource_id=incident_id,
                permission=permission,
            )
        )


def test_readable_event_does_not_allow_diagnosis_write():
    owner = fixture_client("engineer")
    reader, user_id, admin = new_scoped_client(["FIELD_ENGINEER"])
    created = owner.post(
        "/api/incidents", json={"raw_description": "A203"}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert created.status_code == 200
    incident_id = created.json()["incident_id"]
    url = f"/api/incidents/{incident_id}"
    assert reader.get(url).status_code == 404
    assert (
        reader.post(
            url + "/diagnoses", json={}, headers={"Idempotency-Key": uuid4().hex}
        ).status_code
        == 404
    )
    grant_incident(admin, incident_id, user_id, "READ")
    assert reader.get(url).status_code == 200
    response = reader.post(url + "/diagnoses", json={}, headers={"Idempotency-Key": uuid4().hex})
    assert response.status_code == 403
    assert response.json()["code"] == "ACTION_FORBIDDEN"


def test_write_scope_does_not_grant_business_role_or_electrical_qualification():
    client, user_id, admin = new_scoped_client(["EXPERT"])
    created = client.post(
        "/api/incidents", json={"raw_description": "A203"}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert created.status_code == 200
    with Session(admin) as db:
        user = db.get(User, user_id)
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        assert qualifications(db, actor) == ()
        assert "CASE_REVIEWER" not in actor.roles
    reviewer, reviewer_id, _ = new_scoped_client(["CASE_REVIEWER"])
    incident_id = created.json()["incident_id"]
    grant_incident(admin, incident_id, reviewer_id, "WRITE")
    assert reviewer.get(f"/api/incidents/{incident_id}").status_code == 200
    assert (
        reviewer.post(
            f"/api/incidents/{incident_id}/diagnoses",
            json={},
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 403
    )


def test_asset_identity_never_grants_access_to_another_event():
    owner = fixture_client("engineer")
    other = fixture_client("expert")
    created = owner.post(
        "/api/incidents",
        json={"raw_description": "A203", "asset_id": "demo-apx240-001"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 200
    assert other.get("/api/assets/demo-apx240-001").status_code == 200
    assert other.get(f"/api/incidents/{created.json()['incident_id']}").status_code == 404


def test_source_scope_requires_valid_grant_and_policy_and_does_not_approve_egress():
    client = fixture_client("engineer")
    actor_id = client.get("/api/me").json()["user_id"]
    admin = create_engine(settings().migration_database_url.get_secret_value())
    with Session(admin) as db:
        user = db.get(User, actor_id)
        actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
        ids = authorized_source_ids(db, actor)
        assert ids
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "SOURCE", PolicyBinding.resource_id == ids[0]
            )
        )
        assert policy.egress == "DENY"
        require_resource(db, actor, "SOURCE", ids[0])
        receipt = authorize_egress(
            (
                ProcessingGrant(
                    policy.id, policy.version, policy.origin, egress=policy.egress, readable=True
                ),
            ),
            ProviderDataProfile(
                "jev",
                "https://api.typesafe.ai/v1/systemone",
                "test-v1",
                "fixture-terms",
                datetime.now(UTC),
                True,
                ("EXAM_SOURCE",),
            ),
            "PASSAGE_RELEVANCE",
            {},
        )
        assert receipt.decision == "SKIPPED_POLICY"
        assert receipt.input_hash is None
        grant = db.scalar(
            select(ResourceGrant).where(
                ResourceGrant.user_id == actor.id,
                ResourceGrant.resource_type == "SOURCE",
                ResourceGrant.resource_id == ids[0],
                ResourceGrant.active.is_(True),
            )
        )
        grant.permission = "UNRECOGNIZED"
        db.flush()
        assert ids[0] not in authorized_source_ids(db, actor)
        # Transaction rollback preserves the demo's existing grants.


def test_baseline_alarm_and_safety_sources_are_scoped_and_no_case_reviewer_shortcut():
    from app.knowledge.models import SourceRecord

    admin = create_engine(settings().migration_database_url.get_secret_value())
    with Session(admin) as db:
        engineer = db.scalar(select(User).where(User.username == "engineer"))
        actor = ActorContext(
            engineer.id, engineer.organization_id, tuple(engineer.roles), engineer.auth_version
        )
        keys = set(
            db.scalars(
                select(SourceRecord.source_key).where(
                    SourceRecord.id.in_(authorized_source_ids(db, actor))
                )
            )
        )
        assert {
            "SAFE-01",
            "SAFE-02",
            "SAFE-03",
            "SAFE-04",
            "SAFE-05",
            "A101",
            "A203",
            "A205",
            "A310",
            "A401",
            "A520",
            "A900",
        } <= keys
        reviewer = db.scalar(select(User).where(User.username == "reviewer"))
        review_actor = ActorContext(
            reviewer.id, reviewer.organization_id, tuple(reviewer.roles), reviewer.auth_version
        )
        assert authorized_source_ids(db, review_actor) == []


def test_policy_denial_and_wrong_organization_remain_hidden():
    owner = fixture_client("engineer")
    other, user_id, admin = new_scoped_client(["FIELD_ENGINEER"])
    created = owner.post(
        "/api/incidents", json={"raw_description": "A203"}, headers={"Idempotency-Key": uuid4().hex}
    )
    incident_id = created.json()["incident_id"]
    with Session(admin) as db, db.begin():
        db.add(
            ResourceGrant(
                user_id=user_id,
                resource_type="INCIDENT",
                resource_id=incident_id,
                permission="WRITE",
            )
        )
    assert other.get(f"/api/incidents/{incident_id}").status_code == 404
    grant_incident(admin, incident_id, user_id, "WRITE")
    with Session(admin) as db, db.begin():
        user = db.get(User, user_id)
        user.organization_id = "another-organization"
    assert other.get(f"/api/incidents/{incident_id}").status_code == 404
