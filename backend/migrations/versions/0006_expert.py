from alembic import op

from app.expert.models import ExpertReview

revision = "0006_expert"
down_revision = "0005c_events"


def upgrade():
    ExpertReview.__table__.create(op.get_bind())


def downgrade():
    ExpertReview.__table__.drop(op.get_bind())
