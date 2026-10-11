from uuid import uuid4

import pytest

from app.diagnosis.ledger import BudgetLedger, CallReservation, reserve, settle
from app.shared.db import session_factory
from app.shared.errors import DomainError


def test_reserved_budget_persists_and_unknown_usage_is_not_zero():
    ledger_id, reservation_id = str(uuid4()), uuid4().hex
    with session_factory()() as db, db.begin():
        db.add(BudgetLedger(id=ledger_id, counters={}))
        db.flush()
        reserve(db, ledger_id, reservation_id, {"tokens": 2000, "tools": 1})
        db.flush()
        settle(db, reservation_id, None)
    with session_factory()() as db, db.begin():
        ledger = db.get(BudgetLedger, ledger_id)
        assert ledger.counters == {"tokens": 2000, "tools": 1}
        assert db.get(CallReservation, reservation_id).status == "UNKNOWN"
        with pytest.raises(DomainError):
            reserve(db, ledger_id, uuid4().hex, {"tokens": 10001})
        reserve(db, ledger_id, uuid4().hex, {"resumes": 1})
        assert ledger.counters["tokens"] == 2000
