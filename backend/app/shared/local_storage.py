from pathlib import Path

from app.shared.errors import DomainError
from app.shared.storage import StoredObject, checked_key, digest


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        path = (self.root / checked_key(key)).resolve()
        if path.parent != self.root:
            raise DomainError("INVALID_OBJECT_KEY")
        return path

    def put(self, data: bytes, content_type: str) -> StoredObject:
        key = digest(data)
        path = self.path(key)
        try:
            with path.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            if digest(path.read_bytes()) != key:
                raise DomainError("STORAGE_CHECKSUM_MISMATCH", 500) from None
        return StoredObject(key=key, sha256=key, size=len(data))

    def get(self, key: str) -> bytes:
        path = self.path(key)
        if not path.is_file():
            raise DomainError("NOT_FOUND", 404)
        data = path.read_bytes()
        if digest(data) != key:
            raise DomainError("STORAGE_CHECKSUM_MISMATCH", 500)
        return data
