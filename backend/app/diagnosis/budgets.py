from uuid import uuid4

from sqlalchemy.orm import Session

from app.diagnosis.ledger import LIMITS, BudgetLedger, reserve
from app.shared.errors import DomainError


def charge(db: Session, ledger_id: str, **amounts: int) -> None:
    reserve(db, ledger_id, uuid4().hex, amounts)


def require_available(db: Session, ledger_id: str) -> BudgetLedger:
    ledger = db.get(BudgetLedger, ledger_id)
    if not ledger or any(ledger.counters.get(key, 0) > value for key, value in LIMITS.items()):
        raise DomainError("BUDGET_EXHAUSTED", 409)
    return ledger
