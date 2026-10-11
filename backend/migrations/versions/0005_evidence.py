import sqlalchemy as sa
from alembic import op

from app.evidence.models import MediaAsset

revision = "0005_evidence"
down_revision = "0004g_linked_runs"


def upgrade():
    MediaAsset.__table__.create(op.get_bind())
    op.add_column("evidence_versions", sa.Column("media_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "evidence_media_fk", "evidence_versions", "media_assets", ["media_id"], ["id"]
    )
    for name in ("locators", "provenance"):
        op.add_column(
            "evidence_versions", sa.Column(name, sa.JSON(), nullable=False, server_default="{}")
        )
    op.alter_column("evidence_versions", "reviewer_id", nullable=True)
    op.create_check_constraint(
        "evidence_confirmed_reviewer",
        "evidence_versions",
        "state NOT IN ('CONFIRMED','CORRECTED') OR reviewer_id IS NOT NULL",
    )
    op.execute("""CREATE FUNCTION validate_media_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.media_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM media_assets WHERE id=NEW.media_id AND incident_id=NEW.incident_id) THEN
        RAISE EXCEPTION 'MEDIA_EVIDENCE_INCIDENT_MISMATCH';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER evidence_media_binding BEFORE INSERT ON evidence_versions
      FOR EACH ROW EXECUTE FUNCTION validate_media_evidence();
    CREATE FUNCTION preserve_media_input() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.checksum<>NEW.checksum OR OLD.storage_ref<>NEW.storage_ref
        OR OLD.incident_id<>NEW.incident_id OR OLD.created_by<>NEW.created_by
        OR OLD.lineage::jsonb<>NEW.lineage::jsonb THEN
        RAISE EXCEPTION 'MEDIA_INPUT_IMMUTABLE';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER media_input_immutable BEFORE UPDATE ON media_assets
      FOR EACH ROW EXECUTE FUNCTION preserve_media_input();
    CREATE TRIGGER media_no_delete BEFORE DELETE ON media_assets
      FOR EACH ROW EXECUTE FUNCTION reject_record_mutation();""")


def downgrade():
    op.execute("DROP TRIGGER evidence_media_binding ON evidence_versions")
    op.execute("DROP FUNCTION validate_media_evidence()")
    op.drop_constraint("evidence_confirmed_reviewer", "evidence_versions", type_="check")
    op.drop_constraint("evidence_media_fk", "evidence_versions", type_="foreignkey")
    for name in ("media_id", "locators", "provenance"):
        op.drop_column("evidence_versions", name)
    MediaAsset.__table__.drop(op.get_bind())
    op.execute("DROP FUNCTION preserve_media_input()")
