from alembic import op

revision = "0004c_evidence_constraints"
down_revision = "0004b_service_policy"


def upgrade():
    op.create_check_constraint(
        "ck_evidence_state",
        "evidence_versions",
        "state IN ('CANDIDATE','CONFIRMED','CORRECTED','REJECTED','UNAVAILABLE')",
    )
    op.create_check_constraint("ck_evidence_version", "evidence_versions", "version > 0")


def downgrade():
    op.drop_constraint("ck_evidence_version", "evidence_versions", type_="check")
    op.drop_constraint("ck_evidence_state", "evidence_versions", type_="check")
