import sqlalchemy as sa
from alembic import op

from app.diagnosis.release_models import ReportReleaseDecision, ValidationProof
from app.knowledge.assessment_models import CitationAssessment, ClaimReview, RetrievalAssessment
from app.knowledge.template_models import TemplateRegistry

revision = "0004a_assessment"
down_revision = "0004_diagnosis"
TABLES = [
    RetrievalAssessment,
    ClaimReview,
    CitationAssessment,
    TemplateRegistry,
    ValidationProof,
    ReportReleaseDecision,
]


def upgrade():
    for model in TABLES:
        if model is RetrievalAssessment:
            # Preserve the original schema; 0004e adds governance records and references.
            op.create_table(
                "retrieval_assessments",
                sa.Column("id", sa.String(36), primary_key=True),
                sa.Column(
                    "run_id", sa.String(36), sa.ForeignKey("diagnosis_runs.id"), nullable=False
                ),
                sa.Column(
                    "source_id", sa.String(36), sa.ForeignKey("source_records.id"), nullable=False
                ),
                sa.Column("payload", sa.JSON(), nullable=False),
            )
        else:
            model.__table__.create(op.get_bind())
        if model is not TemplateRegistry:
            op.execute(
                f"CREATE TRIGGER {model.__tablename__}_append_only "
                f"BEFORE UPDATE OR DELETE ON {model.__tablename__} "
                "FOR EACH ROW EXECUTE FUNCTION reject_record_mutation()"
            )


def downgrade():
    for model in reversed(TABLES):
        model.__table__.drop(op.get_bind())
