import sqlalchemy as sa
from alembic import op

from app.knowledge.assessment_models import (
    AssessmentCache,
    EgressReceiptRecord,
    ProviderProfileRecord,
)

revision = "0004e_assessment_governance"
down_revision = "0004d_diagnosis_integrity"
TABLES = [ProviderProfileRecord, EgressReceiptRecord, AssessmentCache]


def upgrade():
    for model in TABLES:
        model.__table__.create(op.get_bind())
        op.execute(
            f"CREATE TRIGGER {model.__tablename__}_append_only BEFORE UPDATE OR DELETE "
            f"ON {model.__tablename__} FOR EACH ROW EXECUTE FUNCTION reject_record_mutation()"
        )
    op.add_column(
        "retrieval_assessments",
        sa.Column("provenance", sa.JSON(), nullable=False, server_default="{}"),
    )
    for name, target, length in [
        ("profile_id", "provider_profile_records", 64),
        ("receipt_id", "egress_receipt_records", 36),
    ]:
        op.add_column("retrieval_assessments", sa.Column(name, sa.String(length), nullable=True))
        op.create_foreign_key(
            f"assessment_{name}_fk", "retrieval_assessments", target, [name], ["id"]
        )


def downgrade():
    for name in ("receipt_id", "profile_id"):
        op.drop_constraint(f"assessment_{name}_fk", "retrieval_assessments", type_="foreignkey")
        op.drop_column("retrieval_assessments", name)
    op.drop_column("retrieval_assessments", "provenance")
    for model in reversed(TABLES):
        model.__table__.drop(op.get_bind())
