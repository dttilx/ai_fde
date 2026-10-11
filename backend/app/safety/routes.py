from fastapi import APIRouter, Depends

from app.safety.rules import RULES, VERSION
from app.shared.auth_context import ActorContext, current_actor

router = APIRouter(prefix="/api/safety")


@router.get("/rules")
def rules(actor: ActorContext = Depends(current_actor)):
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    return {
        "version": VERSION,
        "rules": [
            {"rule_id": r.rule_id, "page": r.page, "requirement": r.requirement} for r in RULES
        ],
    }
