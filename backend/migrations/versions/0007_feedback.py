from alembic import op

from app.feedback.models import CaseDraft, RepairOutcome, VerifiedCase

revision = "0007_feedback"
down_revision = "0006_expert"


def upgrade():
    bind = op.get_bind()
    RepairOutcome.__table__.create(bind)
    CaseDraft.__table__.create(bind)
    VerifiedCase.__table__.create(bind)


def downgrade():
    bind = op.get_bind()
    VerifiedCase.__table__.drop(bind)
    CaseDraft.__table__.drop(bind)
    RepairOutcome.__table__.drop(bind)
