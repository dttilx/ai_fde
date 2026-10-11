from alembic import op

from app.access.models import (
    LoginThrottle,
    PolicyBinding,
    QualificationGrant,
    ResourceGrant,
    User,
    UserSession,
)
from app.shared.audit import AuditRecord

revision = "0001a_access"
down_revision = "0000_foundation"
TABLES = [
    User,
    UserSession,
    ResourceGrant,
    QualificationGrant,
    PolicyBinding,
    LoginThrottle,
    AuditRecord,
]


def upgrade():
    for model in TABLES:
        model.__table__.create(op.get_bind())
    op.execute("""
    CREATE FUNCTION reject_record_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'APPEND_ONLY_RECORD'; END; $$;
    CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_records
    FOR EACH ROW EXECUTE FUNCTION reject_record_mutation();
    """)


def downgrade():
    for model in reversed(TABLES):
        model.__table__.drop(op.get_bind())
    op.execute("DROP FUNCTION reject_record_mutation()")
