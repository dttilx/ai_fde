import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.knowledge.manual_ingest import import_manual
from app.knowledge.policy import bind_exam_policies
from app.shared.config import settings

engine = create_engine(settings().migration_database_url.get_secret_value())
with Session(engine) as db, db.begin():
    release = import_manual(db)
    bind_exam_policies(db, release.id)
    print(f"Private knowledge release: {release.id}; mode=FIXTURE; external processing=DENY")
