from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.access.models import UserSession
from app.access.schemas import LoginInput
from app.access.session import login
from app.shared.audit import AuditRecord
from app.shared.auth_context import ActorContext, current_actor, token_hash
from app.shared.config import settings
from app.shared.db import get_db
from app.shared.errors import DomainError

router = APIRouter(prefix="/api")


@router.post("/session")
def create_session(
    body: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)
):
    origin = request.headers.get("origin")
    if origin and origin not in {
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3010",
        "http://localhost:3010",
    }:
        raise DomainError("ORIGIN_FORBIDDEN", 403)
    token, csrf, user = login(
        db, body.username, body.password, request.client.host if request.client else "unknown"
    )
    response.set_cookie(
        "apx_session",
        token,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        max_age=settings().session_seconds,
    )
    return {"user_id": user.id, "username": user.username, "roles": user.roles, "csrf_token": csrf}


@router.delete("/session", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("apx_session", "")
    session = db.get(UserSession, token_hash(token)) if token else None
    if session:
        current_actor(request, db)  # CSRF is still required for a live session.
        db.add(
            AuditRecord(
                actor_id=session.user_id,
                actor_version=str(session.auth_version),
                action="SESSION_REVOKED",
                resource_id=session.user_id,
                details={},
            )
        )
        db.delete(session)
        db.commit()
    response.delete_cookie("apx_session")


@router.get("/me")
def me(actor: ActorContext = Depends(current_actor)):
    return {"user_id": actor.id, "roles": actor.roles, "auth_version": actor.auth_version}
