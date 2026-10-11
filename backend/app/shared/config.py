from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8-sig", extra="ignore"
    )
    database_url: SecretStr
    migration_database_url: SecretStr
    provider_mode: Literal["FIXTURE", "REAL_LOCAL", "REAL_APPROVED_EXTERNAL"] = "FIXTURE"
    ocr_provider: Literal["fixture", "rapidocr"] = "fixture"
    jev_api_key: SecretStr | None = None
    jev_model: str | None = None
    jev_profile_path: Path = PROJECT_ROOT / ".private" / "jev-profile.json"
    storage_provider: Literal["minio", "filesystem"] = "minio"
    minio_endpoint: str = "127.0.0.1:59000"
    minio_bucket: str = "apx240-media"
    minio_app_user: str = "apx_media_service"
    minio_app_password: SecretStr
    media_root: Path = PROJECT_ROOT / ".private" / "media"
    cookie_secure: bool = True
    externally_accessible: bool = False
    session_seconds: int = 28800


@lru_cache
def settings() -> Settings:
    return Settings()
