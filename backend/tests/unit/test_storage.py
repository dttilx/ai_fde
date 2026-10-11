import pytest

from app.shared.errors import DomainError
from app.shared.local_storage import LocalStorage


def test_content_addressing_and_path_rejection(tmp_path):
    store = LocalStorage(tmp_path)
    first = store.put(b"fixture image", "application/octet-stream")
    assert store.put(b"fixture image", "application/octet-stream") == first
    assert store.get(first.key) == b"fixture image"
    with pytest.raises(DomainError):
        store.get("../../.env")
