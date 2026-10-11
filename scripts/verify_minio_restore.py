"""Non-destructive MinIO backup/restore drill in an isolated temporary bucket."""

from __future__ import annotations

import hashlib
import os
import secrets
from io import BytesIO
from pathlib import Path

from minio import Minio

ROOT = Path(__file__).resolve().parents[1]


def env_file(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{name}_NOT_CONFIGURED")


def main() -> None:
    endpoint = env_file("MINIO_ENDPOINT")
    client = Minio(
        endpoint,
        env_file("MINIO_ROOT_USER"),
        env_file("MINIO_ROOT_PASSWORD"),
        secure=False,
    )
    bucket = "apx-restore-drill-" + secrets.token_hex(6)
    key = "fixture/sentinel.bin"
    payload = b"APX240-MINIO-RESTORE-DRILL-v1\n"
    checksum = hashlib.sha256(payload).hexdigest()
    backup_dir = ROOT / ".private" / "backups" / bucket
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_file = backup_dir / key.replace("/", "__")
    try:
        client.make_bucket(bucket)
        client.put_object(
            bucket,
            key,
            BytesIO(payload),
            len(payload),
            content_type="application/octet-stream",
        )
        response = client.get_object(bucket, key)
        try:
            backup_file.write_bytes(response.read())
        finally:
            response.close()
            response.release_conn()
        client.remove_object(bucket, key)
        restored_payload = backup_file.read_bytes()
        client.put_object(bucket, key, BytesIO(restored_payload), len(restored_payload))
        response = client.get_object(bucket, key)
        try:
            restored = response.read()
        finally:
            response.close()
            response.release_conn()
        if hashlib.sha256(restored).hexdigest() != checksum:
            raise RuntimeError("RESTORED_MEDIA_CHECKSUM_FAILED")
        print(
            {
                "status": "MINIO_ISOLATED_RESTORE_PASSED",
                "bucket": bucket,
                "object": key,
                "checksum": checksum,
                "production_bucket_touched": False,
            }
        )
    finally:
        if client.bucket_exists(bucket):
            for item in client.list_objects(bucket, recursive=True):
                client.remove_object(bucket, item.object_name)
            client.remove_bucket(bucket)


if __name__ == "__main__":
    main()
