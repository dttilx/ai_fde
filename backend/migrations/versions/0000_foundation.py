from alembic import op

revision = "0000_foundation"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade():
    # Shared extension intentionally retained; later migrations own their application tables.
    pass
