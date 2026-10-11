import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from app.shared.errors import DomainError


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size: int


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_key(key: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", key):
        raise DomainError("INVALID_OBJECT_KEY")
    return key


class StorageProvider(Protocol):
    def put(self, data: bytes, content_type: str) -> StoredObject: ...
    def get(self, key: str) -> bytes: ...


def storage() -> StorageProvider:
    from app.shared.config import settings
    from app.shared.local_storage import LocalStorage
    from app.shared.minio_storage import MinioStorage

    config = settings()
    if config.storage_provider == "filesystem":
        return LocalStorage(config.media_root)
    return MinioStorage(config)
