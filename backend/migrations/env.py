from alembic import context
from sqlalchemy import create_engine

from app.shared.config import settings
from app.shared.db import Base


def offline():
    context.configure(
        url=settings().migration_database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def online():
    engine = create_engine(settings().migration_database_url.get_secret_value())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    offline()
else:
    online()
