from alembic import op


revision = "0008_feedback_integrity"
down_revision = "0007_feedback"


def upgrade():
    # Repair results are append-only evidence. CaseDraft and VerifiedCase remain
    # mutable workflow projections so review and publication can advance safely.
    op.execute(
        """CREATE TRIGGER repair_outcomes_append_only
        BEFORE UPDATE OR DELETE ON repair_outcomes
        FOR EACH ROW EXECUTE FUNCTION reject_record_mutation()"""
    )


def downgrade():
    op.execute("DROP TRIGGER repair_outcomes_append_only ON repair_outcomes")
