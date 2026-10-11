from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.shared.db import Base
from app.shared.errors import DomainError

LIMITS = {
    "steps": 32,
    "retrievals": 3,
    "questions": 5,
    "tools": 20,
    "tokens": 12000,
    "resumes": 5,
    "active_ms": 120000,
}


class BudgetLedger(Base):
    __tablename__ = "budget_ledgers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    counters: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=0)


class CallReservation(Base):
    __tablename__ = "call_reservations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ledger_id: Mapped[str] = mapped_column(String(36))
    amounts: Mapped[dict] = mapped_column(JSON)
    actual_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RESERVED")


def reserve(db: Session, ledger_id: str, reservation_id: str, amounts: dict[str, int]) -> None:
    ledger = db.get(BudgetLedger, ledger_id, with_for_update=True)
    if ledger is None:
        raise DomainError("BUDGET_LEDGER_MISSING", 409)
    if db.get(CallReservation, reservation_id):
        raise DomainError("RESERVATION_ALREADY_EXISTS", 409)
    counters = dict(ledger.counters)
    if any(counters.get(metric, 0) > limit for metric, limit in LIMITS.items()):
        raise DomainError("BUDGET_EXHAUSTED", 409)
    for metric, amount in amounts.items():
        if metric not in LIMITS or amount < 0:
            raise DomainError("INVALID_BUDGET_AMOUNT")
        if counters.get(metric, 0) + amount > LIMITS[metric]:
            raise DomainError("BUDGET_EXHAUSTED", 409)
        counters[metric] = counters.get(metric, 0) + amount
    ledger.counters = counters
    ledger.version += 1
    db.add(CallReservation(id=reservation_id, ledger_id=ledger_id, amounts=amounts))


def settle(db: Session, reservation_id: str, actual_tokens: int | None) -> None:
    reservation = db.get(CallReservation, reservation_id, with_for_update=True)
    if not reservation or reservation.status != "RESERVED":
        raise DomainError("RESERVATION_NOT_ACTIVE", 409)
    if actual_tokens is not None:
        if actual_tokens < 0:
            raise DomainError("INVALID_TOKEN_USAGE")
        ledger = db.get(BudgetLedger, reservation.ledger_id, with_for_update=True)
        if ledger is None:
            raise DomainError("BUDGET_LEDGER_MISSING", 409)
        # Unknown usage keeps the entire conservative token reservation; known usage reconciles it.
        counters = dict(ledger.counters)
        counters["tokens"] = (
            counters.get("tokens", 0) - reservation.amounts.get("tokens", 0) + actual_tokens
        )
        ledger.counters = counters
        ledger.version += 1
    reservation.actual_tokens = actual_tokens
    reservation.status = "UNKNOWN" if actual_tokens is None else "SETTLED"
