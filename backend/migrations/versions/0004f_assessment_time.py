import sqlalchemy as sa
from alembic import op

revision = "0004f_assessment_time"
down_revision = "0004e_assessment_governance"


def upgrade():
    # Older timestamps are unknown; do not pretend migration time was evaluation time.
    op.add_column(
        "retrieval_assessments", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    op.drop_column("retrieval_assessments", "created_at")
