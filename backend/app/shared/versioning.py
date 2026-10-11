import hashlib
import json
from typing import Any


def content_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def effect_key(run: str, node: str, snapshot_hash: str, effect: str) -> str:
    return content_hash([run, node, snapshot_hash, effect])
