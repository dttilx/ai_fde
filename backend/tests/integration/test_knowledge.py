from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.knowledge.manual_ingest import CONFIG, import_manual
from app.knowledge.models import SourceRecord
from app.shared.config import settings


def test_import_is_idempotent_and_changed_config_creates_release():
    engine = create_engine(settings().migration_database_url.get_secret_value())
    with Session(engine) as db, db.begin():
        first = import_manual(db)
        assert import_manual(db).id == first.id
        second = import_manual(db, config={**CONFIG, "chunk_chars": 650})
        assert second.id != first.id
        records = db.scalars(select(SourceRecord).where(SourceRecord.release_id == first.id)).all()
        by_key = {record.source_key: record for record in records}
        assert by_key["SAFE-01"].locator["page"] == 3
        assert by_key["A203"].locator["page"] == 4
        assert by_key["H02"].locator["page"] == 5
        assert by_key["WO-240-042"].locator["page"] == 6
        assert by_key["MANUAL-P2"].metadata_fields["extraction_warning"] == "UNMAPPED_GLYPH"
