"""Deterministic offline index utilities; hash vectors do not model semantic similarity."""

import hashlib
import re
from collections.abc import Sequence

from app.knowledge.models import SourceRecord

KEYWORDS = ("加热", "温度", "电流", "压力", "漏气", "联锁", "卡阻", "通信")


def fixture_embedding(text: str) -> list[float]:
    return [(value - 127.5) / 127.5 for value in hashlib.sha256(text.encode()).digest()[:16]]


def query_tokens(alarm: str, query: str) -> list[str]:
    identifiers = re.findall(
        r"(?<![A-Za-z0-9])(?:A\d{3}|H\d{2}|WO-240-\d{3})(?![A-Za-z0-9])", query
    )
    return list(
        dict.fromkeys([alarm, *identifiers, *(word for word in KEYWORDS if word in query)])
    )[:8]


def fuse_rankings(rankings: Sequence[Sequence[SourceRecord]]) -> list[tuple[SourceRecord, float]]:
    scores: dict[str, float] = {}
    objects: dict[str, SourceRecord] = {}
    for ranking in rankings:
        for rank, record in enumerate(ranking, 1):
            scores[record.id] = scores.get(record.id, 0) + 1 / (60 + rank)
            objects[record.id] = record
    return [
        (objects[key], scores[key]) for key in sorted(scores, key=lambda key: (-scores[key], key))
    ]
