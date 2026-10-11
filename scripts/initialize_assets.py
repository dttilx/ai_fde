import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.incidents.assets import initialize_demo_assets
from app.shared.config import settings

with Session(create_engine(settings().migration_database_url.get_secret_value())) as db, db.begin():
    initialize_demo_assets(db)
print("Synthetic demo assets initialized; warranty UNKNOWN, QR does not grant access.")
