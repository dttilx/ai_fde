"""Local fixture setup. Simulated approval cannot approve a real-model template."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.knowledge.manual_ingest import import_manual
from app.knowledge.template_registry import simulate_fixture_approval, stage_template
from app.shared.config import settings

parser = argparse.ArgumentParser()
parser.add_argument("--simulate-fixture-approval", action="store_true")
parser.add_argument("--fixture-reviewer", default="expert")
args = parser.parse_args()
engine = create_engine(settings().migration_database_url.get_secret_value())
with Session(engine) as db, db.begin():
    release = import_manual(db)
    for alarm in ("A203", "A310"):
        row = stage_template(db, release.id, alarm)
        if args.simulate_fixture_approval:
            simulate_fixture_approval(db, row, args.fixture_reviewer)
        print(f"Template {row.id}: {row.status}; FIXTURE ONLY; no real human approval claimed")
