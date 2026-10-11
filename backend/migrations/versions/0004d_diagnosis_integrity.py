"""Add database guards without changing or replacing existing diagnosis history."""

from alembic import op

revision = "0004d_diagnosis_integrity"
down_revision = "0004c_evidence_constraints"

STATUSES = (
    "PREPARING",
    "SAFETY_CHECK",
    "RETRIEVING",
    "NEEDS_INFORMATION",
    "WAITING_EXPERT",
    "CONFLICT_BLOCKED",
    "FINALIZING",
    "COMPLETED",
    "ESCALATED",
    "FAILED",
)


def upgrade():
    values = ", ".join(f"'{status}'" for status in STATUSES)
    op.create_check_constraint("run_status_valid", "diagnosis_runs", f"status IN ({values})")
    op.create_check_constraint(
        "run_checkpoint_nonnegative", "diagnosis_runs", "checkpoint_version >= 0"
    )
    op.create_check_constraint(
        "resume_version_nonnegative", "resume_requests", "expected_version >= 0"
    )
    op.execute("""CREATE OR REPLACE FUNCTION preserve_run_scope()
      RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.source_scope::jsonb IS DISTINCT FROM NEW.source_scope::jsonb
           OR OLD.ledger_id IS DISTINCT FROM NEW.ledger_id
           OR OLD.graph_thread_id IS DISTINCT FROM NEW.graph_thread_id
           OR OLD.incident_id IS DISTINCT FROM NEW.incident_id
           OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
           OR OLD.actor_version IS DISTINCT FROM NEW.actor_version THEN
          RAISE EXCEPTION 'RUN_SCOPE_IMMUTABLE';
        END IF;
        IF NEW.checkpoint_version < OLD.checkpoint_version
           OR NEW.checkpoint_version > OLD.checkpoint_version + 1 THEN
          RAISE EXCEPTION 'CHECKPOINT_VERSION_INVALID';
        END IF;
        RETURN NEW;
      END; $$;""")
    op.execute("""CREATE FUNCTION validate_run_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM evidence_snapshots
          WHERE id = NEW.snapshot_id AND incident_id = NEW.incident_id) THEN
          RAISE EXCEPTION 'SNAPSHOT_INCIDENT_MISMATCH';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER run_snapshot_binding BEFORE INSERT OR UPDATE ON diagnosis_runs
      FOR EACH ROW EXECUTE FUNCTION validate_run_snapshot();""")
    op.execute("""CREATE FUNCTION validate_citation_release() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM source_records
          WHERE id = NEW.source_id AND release_id = NEW.release_id) THEN
          RAISE EXCEPTION 'CITATION_RELEASE_MISMATCH';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER citation_release_binding BEFORE INSERT ON citations
      FOR EACH ROW EXECUTE FUNCTION validate_citation_release();""")
    op.execute("""CREATE FUNCTION preserve_human_action() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'HUMAN_ACTION_IMMUTABLE'; END IF;
        IF OLD.run_id IS DISTINCT FROM NEW.run_id
           OR OLD.snapshot_hash IS DISTINCT FROM NEW.snapshot_hash
           OR OLD.kind IS DISTINCT FROM NEW.kind
           OR OLD.reasons::jsonb IS DISTINCT FROM NEW.reasons::jsonb THEN
          RAISE EXCEPTION 'HUMAN_ACTION_IMMUTABLE';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER human_action_immutable BEFORE UPDATE OR DELETE ON pending_human_actions
      FOR EACH ROW EXECUTE FUNCTION preserve_human_action();""")


def downgrade():
    op.execute("DROP TRIGGER human_action_immutable ON pending_human_actions")
    op.execute("DROP FUNCTION preserve_human_action()")
    op.execute("DROP TRIGGER citation_release_binding ON citations")
    op.execute("DROP FUNCTION validate_citation_release()")
    op.execute("DROP TRIGGER run_snapshot_binding ON diagnosis_runs")
    op.execute("DROP FUNCTION validate_run_snapshot()")
    op.drop_constraint("resume_version_nonnegative", "resume_requests", type_="check")
    op.drop_constraint("run_checkpoint_nonnegative", "diagnosis_runs", type_="check")
    op.drop_constraint("run_status_valid", "diagnosis_runs", type_="check")
    op.execute("""CREATE OR REPLACE FUNCTION preserve_run_scope()
      RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.source_scope::jsonb IS DISTINCT FROM NEW.source_scope::jsonb
           OR OLD.ledger_id IS DISTINCT FROM NEW.ledger_id
           OR OLD.graph_thread_id IS DISTINCT FROM NEW.graph_thread_id THEN
          RAISE EXCEPTION 'RUN_SCOPE_IMMUTABLE';
        END IF;
        RETURN NEW;
      END; $$;""")
