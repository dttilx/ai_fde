import os
from contextlib import contextmanager

# Diagnostics and checkpoints are confidential; external tracing is not a default provider.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langgraph.checkpoint.postgres import PostgresSaver

from app.shared.config import settings


def connection_string(admin: bool = False) -> str:
    config = settings()
    value = config.migration_database_url if admin else config.database_url
    return value.get_secret_value().replace("postgresql+psycopg://", "postgresql://", 1)


def initialize_checkpoints() -> None:
    with PostgresSaver.from_conn_string(connection_string(admin=True)) as saver:
        saver.setup()


@contextmanager
def checkpoint_store():
    with PostgresSaver.from_conn_string(connection_string()) as saver:
        yield saver
