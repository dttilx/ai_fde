"""Local administrative initialization; fixture grants are not real maintenance authorization."""
import argparse
import json
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.access.models import QualificationGrant, User
from app.access.session import hasher
from app.shared.config import settings

parser = argparse.ArgumentParser()
parser.add_argument("--create-fixtures", action="store_true")
parser.add_argument("--disable-user")
args = parser.parse_args()
engine = create_engine(settings().migration_database_url.get_secret_value())
with Session(engine) as db:
    if args.disable_user:
        user = db.scalar(select(User).where(User.username == args.disable_user))
        if user is None:
            raise SystemExit("No such local account")
        user.enabled = False
        user.auth_version += 1
        db.commit()
        print("Account disabled; existing sessions no longer authorize requests.")
    elif args.create_fixtures:
        path = ROOT / ".private/demo-credentials.json"
        credentials = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for name, role in [("engineer", "FIELD_ENGINEER"), ("expert", "EXPERT"), ("reviewer", "CASE_REVIEWER")]:
            user = db.scalar(select(User).where(User.username == name))
            if user is None:
                password = secrets.token_urlsafe(24)
                user = User(username=name, password_hash=hasher.hash(password), roles=[role])
                db.add(user)
                db.flush()
                credentials[name] = {"username": name, "password": password, "user_id": user.id}
                if role in {"FIELD_ENGINEER", "EXPERT"}:
                    for qualification in ["ELECTRICAL", "MECHANICAL"]:
                        db.add(QualificationGrant(user_id=user.id, qualification=qualification,
                            scope="APX-240", basis="SELF_AUTHORED_SIMULATION_ONLY",
                            expires_at=datetime.now(UTC) + timedelta(days=30)))
        db.commit()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(credentials, indent=2), encoding="utf-8")
        print("Demo accounts initialized. Read ignored .private/demo-credentials.json locally.")
    else:
        parser.error("Choose --create-fixtures or --disable-user")
