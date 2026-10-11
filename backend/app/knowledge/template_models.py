from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class TemplateRegistry(Base):
    __tablename__ = "template_registry"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    release_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON)
