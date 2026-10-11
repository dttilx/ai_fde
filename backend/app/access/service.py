from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import PolicyBinding, ResourceGrant
from app.shared.auth_context import ActorContext
from app.shared.errors import DomainError


def require_resource(
    db: Session, actor: ActorContext, resource_type: str, resource_id: str, write: bool = False
) -> None:
    grants = db.scalars(
        select(ResourceGrant).where(
            ResourceGrant.user_id == actor.id,
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource_id,
            ResourceGrant.active.is_(True),
            ResourceGrant.permission.in_(("READ", "WRITE")),
        )
    ).all()
    if not grants:
        raise DomainError("NOT_FOUND", 404)
    policy = db.scalar(
        select(PolicyBinding).where(
            PolicyBinding.resource_type == resource_type, PolicyBinding.resource_id == resource_id
        )
    )
    if policy is None or actor.id not in policy.readable_by:
        raise DomainError("NOT_FOUND", 404)
    # Only reveal action denial after proving the resource is visible.
    if write and not any(grant.permission == "WRITE" for grant in grants):
        raise DomainError("ACTION_FORBIDDEN", 403)
