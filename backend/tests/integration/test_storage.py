from app.shared.config import settings
from app.shared.minio_storage import MinioStorage


def test_private_minio_roundtrip():
    store = MinioStorage(settings())
    value = store.put(b"non-sensitive integration fixture", "application/octet-stream")
    assert store.put(b"non-sensitive integration fixture", "application/octet-stream") == value
    assert store.get(value.key) == b"non-sensitive integration fixture"
