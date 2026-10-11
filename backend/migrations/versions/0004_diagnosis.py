from alembic import op

from app.diagnosis.models import (
    Citation,
    DiagnosisRun,
    NodeAudit,
    PendingHumanAction,
    ReportVersion,
    ResumeRequest,
)

revision = "0004_diagnosis"
down_revision = "0003_incidents"
TABLES = [DiagnosisRun, ReportVersion, Citation, ResumeRequest, PendingHumanAction, NodeAudit]


def upgrade():
    for model in TABLES:
        model.__table__.create(op.get_bind())
    for name in ["report_versions", "citations", "resume_requests", "node_audits"]:
        op.execute(
            f"CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION reject_record_mutation()"
        )
    op.execute("""CREATE FUNCTION preserve_run_scope() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.source_scope::jsonb IS DISTINCT FROM NEW.source_scope::jsonb
           OR OLD.ledger_id IS DISTINCT FROM NEW.ledger_id
           OR OLD.graph_thread_id IS DISTINCT FROM NEW.graph_thread_id THEN
          RAISE EXCEPTION 'RUN_SCOPE_IMMUTABLE';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER run_scope_immutable BEFORE UPDATE ON diagnosis_runs
      FOR EACH ROW EXECUTE FUNCTION preserve_run_scope();""")


def downgrade():
    for model in reversed(TABLES):
        model.__table__.drop(op.get_bind())
    op.execute("DROP FUNCTION preserve_run_scope()")
