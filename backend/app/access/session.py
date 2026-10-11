import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access.models import LoginThrottle, User, UserSession
from app.shared.audit import AuditRecord
from app.shared.auth_context import token_hash
from app.shared.config import settings
from app.shared.errors import DomainError

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def login(db: Session, username: str, password: str, peer: str) -> tuple[str, str, User]:
    key = token_hash(f"{peer}:{username}")
    # Serialize throttling for this hashed login target across workers.
    from sqlalchemy import text

    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})
    throttle = db.get(LoginThrottle, key)
    clock = datetime.now(UTC)
    if throttle is None:
        throttle = LoginThrottle(key=key, attempts=0, window_started_at=clock)
        db.add(throttle)
    if clock - throttle.window_started_at > timedelta(minutes=5):
        throttle.attempts = 0
        throttle.window_started_at = clock
    if throttle.attempts >= 10:
        db.commit()
        raise DomainError("LOGIN_THROTTLED", 429)
    user = db.scalar(select(User).where(User.username == username))
    valid: bool
    try:
        valid = hasher.verify(user.password_hash if user else DUMMY_HASH, password)
    except VerifyMismatchError:
        valid = False
    if not user or not user.enabled or not valid:
        throttle.attempts += 1
        db.commit()
        raise DomainError("LOGIN_FAILED", 401)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    throttle.attempts = 0
    db.add(
        AuditRecord(
            actor_id=user.id,
            actor_version=str(user.auth_version),
            action="SESSION_CREATED",
            resource_id=user.id,
            details={"roles": user.roles},
        )
    )
    db.add(
        UserSession(
            token_hash=token_hash(token),
            user_id=user.id,
            csrf_hash=token_hash(csrf),
            auth_version=user.auth_version,
            expires_at=clock + timedelta(seconds=settings().session_seconds),
        )
    )
    db.commit()
    return token, csrf, user
