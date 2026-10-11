from functools import lru_cache
from typing import TypeVar

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.shared.config import settings
from app.shared.errors import DomainError


class Base(DeclarativeBase):
    pass


Record = TypeVar("Record", bound=Base)


def require_record(db: Session, model: type[Record], key: str) -> Record:
    value = db.get(model, key)
    if value is None:
        raise DomainError("PERSISTED_RECORD_MISSING", 409)
    return value


@lru_cache
def engine():
    return create_engine(settings().database_url.get_secret_value(), pool_pre_ping=True)


def session_factory() -> sessionmaker[Session]:
    return sessionmaker(engine(), expire_on_commit=False)


def get_db():
    with session_factory()() as db:
        yield db
