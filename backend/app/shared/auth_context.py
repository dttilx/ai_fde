from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.access.models import User, UserSession
from app.shared.db import get_db
from app.shared.errors import DomainError


def token_hash(value: str) -> str:
    return sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class ActorContext:
    id: str
    organization_id: str
    roles: tuple[str, ...]
    auth_version: int

    def require_role(self, *roles: str) -> None:
        if not set(roles).intersection(self.roles):
            raise DomainError("ROLE_FORBIDDEN", 403)


def current_actor(request: Request, db: Session = Depends(get_db)) -> ActorContext:
    token = request.cookies.get("apx_session", "")
    session = db.get(UserSession, token_hash(token)) if token else None
    if not session or session.expires_at <= datetime.now(UTC):
        raise DomainError("UNAUTHENTICATED", 401)
    user = db.get(User, session.user_id)
    if not user or not user.enabled or user.auth_version != session.auth_version:
        raise DomainError("UNAUTHENTICATED", 401)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = token_hash(request.headers.get("X-CSRF-Token", ""))
        if not compare_digest(supplied, session.csrf_hash):
            raise DomainError("CSRF_INVALID", 403)
    return ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
