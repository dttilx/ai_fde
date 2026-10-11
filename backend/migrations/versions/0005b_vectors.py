from alembic import op

from app.knowledge.vector_models import SourceEmbedding

revision = "0005b_vectors"
down_revision = "0005_evidence"


def upgrade():
    SourceEmbedding.__table__.create(op.get_bind())
    op.execute("""CREATE FUNCTION immutable_source_embedding() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'SOURCE_EMBEDDING_APPEND_ONLY'; END; $$""")
    op.execute("""CREATE TRIGGER source_embedding_immutable BEFORE UPDATE OR DELETE
        ON source_embeddings FOR EACH ROW EXECUTE FUNCTION immutable_source_embedding()""")


def downgrade():
    SourceEmbedding.__table__.drop(op.get_bind())
    op.execute("DROP FUNCTION immutable_source_embedding()")
