from alembic import op

from app.shared.jobs.models import Job, JobEvent

revision = "0001_jobs"
down_revision = "0001a_access"


def upgrade():
    Job.__table__.create(op.get_bind())
    JobEvent.__table__.create(op.get_bind())
    op.execute("""CREATE TRIGGER job_events_append_only BEFORE UPDATE OR DELETE ON job_events
                  FOR EACH ROW EXECUTE FUNCTION reject_record_mutation()""")


def downgrade():
    JobEvent.__table__.drop(op.get_bind())
    Job.__table__.drop(op.get_bind())
