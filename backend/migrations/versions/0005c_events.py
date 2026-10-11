from alembic import op

from app.diagnosis.events import DiagnosisEvent

revision = "0005c_events"
down_revision = "0005b_vectors"


def upgrade():
    DiagnosisEvent.__table__.create(op.get_bind())
    op.execute("""CREATE TRIGGER diagnosis_event_immutable BEFORE UPDATE OR DELETE
    ON diagnosis_events FOR EACH ROW EXECUTE FUNCTION immutable_source_embedding()""")


def downgrade():
    DiagnosisEvent.__table__.drop(op.get_bind())
