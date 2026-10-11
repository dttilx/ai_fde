from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.access.models import PolicyBinding, ResourceGrant, User
from app.evidence.models import MediaAsset
from app.shared.audit import AuditRecord
from app.shared.db import session_factory
from tests.acceptance.test_media_upload import png
from tests.acceptance.test_resource_access import fixture_client


def test_tombstone_is_authorized_idempotent_and_preserves_original_media():
    engineer, expert = fixture_client("engineer"), fixture_client("expert")
    created = engineer.post(
        "/api/incidents", json={"raw_description": "A310"}, headers={"Idempotency-Key": uuid4().hex}
    )
    incident_id = created.json()["incident_id"]
    uploaded = engineer.post(
        f"/api/incidents/{incident_id}/media",
        files={"file": ("retention.png", png(), "image/png")},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert uploaded.status_code == 200
    media_id = uploaded.json()["media_id"]
    with session_factory()() as db, db.begin():
        user = db.scalar(select(User).where(User.username == "expert"))
        media = db.get(MediaAsset, media_id)
        checksum, original_ref = media.checksum, media.storage_ref
        for kind, identifier in [("INCIDENT", incident_id), ("MEDIA", media_id)]:
            db.add(
                ResourceGrant(
                    user_id=user.id, resource_type=kind, resource_id=identifier, permission="WRITE"
                )
            )
            policy = db.scalar(
                select(PolicyBinding).where(
                    PolicyBinding.resource_type == kind, PolicyBinding.resource_id == identifier
                )
            )
            policy.readable_by = [*policy.readable_by, user.id]
    body = {"expected_checksum": checksum, "reason": "本地自测：撤回媒体访问，保留引用"}
    endpoint = f"/api/media/{media_id}/tombstone"
    assert engineer.post(endpoint, json=body).status_code == 403
    assert expert.post(endpoint, json={**body, "expected_checksum": "0" * 64}).status_code == 409
    first = expert.post(endpoint, json=body)
    assert first.status_code == 200, first.text
    assert expert.post(endpoint, json=body).json()["tombstone_id"] == first.json()["tombstone_id"]
    assert engineer.get(f"/api/media/{media_id}/content").status_code == 410
    assert expert.get(f"/api/media/{media_id}/frames/0/content").status_code == 410
    with session_factory()() as db:
        original = db.get(MediaAsset, media_id)
        assert original.checksum == checksum and original.storage_ref == original_ref
        audit = db.get(AuditRecord, first.json()["tombstone_id"])
        assert audit.details["physical_purge"] == "NOT_PERFORMED"
        db.delete(audit)
        with pytest.raises(DBAPIError, match="APPEND_ONLY_RECORD"):
            db.flush()
