"""Shared action guard; trusted identity, visibility and operation are separate checks."""

from sqlalchemy.orm import Session

from app.access.service import require_resource
from app.shared.auth_context import ActorContext


def require_action(
    db: Session,
    actor: ActorContext,
    resource_type: str,
    resource_id: str,
    *roles: str,
) -> None:
    require_resource(db, actor, resource_type, resource_id)
    actor.require_role(*roles)
    require_resource(db, actor, resource_type, resource_id, write=True)
