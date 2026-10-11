import os
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql

from app.diagnosis.checkpoints import connection_string
from app.shared.config import settings


def test_upgrade_downgrade_in_isolated_private_database():
    # Never downgrade the application database or another project's database.
    name = "apx_migration_test_" + uuid4().hex
    with psycopg.connect(connection_string(admin=True), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} OWNER apx_admin").format(sql.Identifier(name)))
        try:
            environment = dict(os.environ)
            url = (
                settings().migration_database_url.get_secret_value().rsplit("/", 1)[0] + "/" + name
            )
            environment["MIGRATION_DATABASE_URL"] = url
            for arguments in [("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")]:
                result = subprocess.run(
                    [sys.executable, "-m", "alembic", *arguments],
                    env=environment,
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0, "Isolated migration failed; inspect migration logic"
        finally:
            # The verified, generated identifier belongs exclusively to this test.
            assert name.startswith("apx_migration_test_")
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
