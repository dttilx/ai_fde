import sqlalchemy as sa
from alembic import op

from app.incidents.models import Asset, Evidence, EvidenceSnapshot, Incident, WarrantyRecord

revision = "0003_incidents"
down_revision = "0002_knowledge"


def upgrade():
    Asset.__table__.create(op.get_bind())
    # Freeze the original warranty schema; later revisions add confirmed version fields.
    op.create_table(
        "warranty_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(100), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("basis_ref", sa.String(100), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
    )
    Incident.__table__.create(op.get_bind())
    op.create_table(
        "evidence_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("evidence_key", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", sa.String(36), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("reviewer_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("incident_id", "evidence_key", "version"),
    )
    EvidenceSnapshot.__table__.create(op.get_bind())
    for name in ["incidents", "evidence_versions", "evidence_snapshots"]:
        op.execute(
            f"CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION reject_record_mutation()"
        )


def downgrade():
    for model in [EvidenceSnapshot, Evidence, Incident, WarrantyRecord, Asset]:
        model.__table__.drop(op.get_bind())
