from alembic import op

from app.diagnosis.ledger import BudgetLedger, CallReservation
from app.shared.invocations import Invocation, Outbox

revision = "0001b_budgets"
down_revision = "0001_jobs"


def upgrade():
    for model in [BudgetLedger, CallReservation, Invocation, Outbox]:
        model.__table__.create(op.get_bind())


def downgrade():
    for model in [Outbox, Invocation, CallReservation, BudgetLedger]:
        model.__table__.drop(op.get_bind())
