from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant, User
from app.knowledge.models import SourceRecord


def bind_exam_policies(db: Session, release_id: str) -> None:
    users = db.scalars(select(User).where(User.enabled.is_(True))).all()
    readers = [user for user in users if {"FIELD_ENGINEER", "EXPERT"}.intersection(user.roles)]
    records = db.scalars(select(SourceRecord).where(SourceRecord.release_id == release_id)).all()
    for source in records:
        policy = db.scalar(
            select(PolicyBinding).where(
                PolicyBinding.resource_type == "SOURCE", PolicyBinding.resource_id == source.id
            )
        )
        if policy is None:
            db.add(
                PolicyBinding(
                    resource_type="SOURCE",
                    resource_id=source.id,
                    classification="FIELD_RECORD"
                    if source.collection == "MAINTENANCE_RECORD"
                    else "TECHNICAL_REFERENCE",
                    origin="EXAM_SOURCE",
                    readable_by=[user.id for user in readers],
                    egress="DENY",
                )
            )
            for user in readers:
                db.add(
                    ResourceGrant(user_id=user.id, resource_type="SOURCE", resource_id=source.id)
                )
