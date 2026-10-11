from alembic import op

from app.diagnosis.models import LinkedRun

revision = "0004g_linked_runs"
down_revision = "0004f_assessment_time"


def upgrade():
    LinkedRun.__table__.create(op.get_bind())
    op.execute("""CREATE FUNCTION validate_linked_run() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM diagnosis_runs p JOIN diagnosis_runs c
        ON c.id = NEW.child_run_id WHERE p.id = NEW.parent_run_id
        AND p.id <> c.id AND p.incident_id = c.incident_id AND p.ledger_id = c.ledger_id
        AND p.source_scope::jsonb <@ c.source_scope::jsonb
        AND p.source_scope::jsonb <> c.source_scope::jsonb AND c.actor_id = NEW.actor_id) THEN
        RAISE EXCEPTION 'LINKED_RUN_BINDING_INVALID';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER linked_run_binding BEFORE INSERT ON linked_diagnosis_runs
      FOR EACH ROW EXECUTE FUNCTION validate_linked_run();
    CREATE TRIGGER linked_runs_append_only BEFORE UPDATE OR DELETE ON linked_diagnosis_runs
      FOR EACH ROW EXECUTE FUNCTION reject_record_mutation();""")


def downgrade():
    LinkedRun.__table__.drop(op.get_bind())
    op.execute("DROP FUNCTION validate_linked_run()")
