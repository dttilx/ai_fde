from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import QualificationGrant
from app.shared.auth_context import ActorContext


def qualification_records(db: Session, actor: ActorContext, scope: str = "APX-240"):
    grants = db.scalars(
        select(QualificationGrant).where(
            QualificationGrant.user_id == actor.id,
            QualificationGrant.active.is_(True),
            QualificationGrant.expires_at > datetime.now(UTC),
            QualificationGrant.scope == scope,
            QualificationGrant.basis != "",
        )
    ).all()
    return [grant for grant in grants if grant.basis.strip()]


def qualifications(db: Session, actor: ActorContext, scope: str = "APX-240") -> tuple[str, ...]:
    return tuple(grant.qualification for grant in qualification_records(db, actor, scope))
