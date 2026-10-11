from alembic import op

from app.knowledge.models import KnowledgeChunk, KnowledgeRelease, SourceRecord

revision = "0002_knowledge"
down_revision = "0001b_budgets"


def upgrade():
    for model in [KnowledgeRelease, SourceRecord, KnowledgeChunk]:
        model.__table__.create(op.get_bind())
        op.execute(
            f"CREATE TRIGGER {model.__tablename__}_append_only "
            f"BEFORE UPDATE OR DELETE ON {model.__tablename__} "
            "FOR EACH ROW EXECUTE FUNCTION reject_record_mutation()"
        )


def downgrade():
    for model in [KnowledgeChunk, SourceRecord, KnowledgeRelease]:
        model.__table__.drop(op.get_bind())
