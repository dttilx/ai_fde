import io

from minio import Minio
from minio.error import S3Error

from app.shared.config import Settings
from app.shared.errors import DomainError
from app.shared.storage import StoredObject, checked_key, digest


class MinioStorage:
    def __init__(self, config: Settings):
        self.bucket = config.minio_bucket
        self.client = Minio(
            config.minio_endpoint,
            access_key=config.minio_app_user,
            secret_key=config.minio_app_password.get_secret_value(),
            secure=False,
        )

    def put(self, data: bytes, content_type: str) -> StoredObject:
        key = digest(data)
        try:
            existing = self.client.stat_object(self.bucket, key)
            if not existing.metadata or existing.metadata.get("x-amz-meta-sha256") != key:
                raise DomainError("STORAGE_CHECKSUM_MISMATCH", 500)
            if existing.size is None:
                raise DomainError("STORAGE_METADATA_INVALID", 500)
            return StoredObject(key=key, sha256=key, size=existing.size)
        except S3Error as exc:
            if exc.code not in {"NoSuchKey", "NoSuchObject"}:
                raise
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(data),
            len(data),
            content_type=content_type,
            metadata={"sha256": key},
        )
        return StoredObject(key=key, sha256=key, size=len(data))

    def get(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, checked_key(key))
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()
        if digest(data) != key:
            raise DomainError("STORAGE_CHECKSUM_MISMATCH", 500)
        return data
