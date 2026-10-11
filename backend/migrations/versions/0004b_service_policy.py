import sqlalchemy as sa
from alembic import op

from app.incidents.models import ServiceRestriction

revision = "0004b_service_policy"
down_revision = "0004a_assessment"


def upgrade():
    op.add_column(
        "warranty_records", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column("warranty_records", sa.Column("confirmed_by", sa.String(36), nullable=True))
    op.add_column(
        "warranty_records", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(
        "uq_warranty_asset_version", "warranty_records", ["asset_id", "version"]
    )
    ServiceRestriction.__table__.create(op.get_bind())
    for name in ("warranty_records", "service_restrictions"):
        op.execute(
            f"CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION reject_record_mutation()"
        )


def downgrade():
    ServiceRestriction.__table__.drop(op.get_bind())
    op.execute("DROP TRIGGER warranty_records_append_only ON warranty_records")
    op.drop_constraint("uq_warranty_asset_version", "warranty_records", type_="unique")
    for column in ("confirmed_at", "confirmed_by", "version"):
        op.drop_column("warranty_records", column)
