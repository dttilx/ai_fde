import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pymupdf
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.knowledge.indexing import fixture_embedding
from app.knowledge.models import KnowledgeChunk, KnowledgeRelease, SourceRecord
from app.shared.config import PROJECT_ROOT
from app.shared.errors import DomainError
from app.shared.versioning import content_hash

CONFIG = {
    "parser": "pymupdf-1.28.2",
    "chunk_chars": 700,
    "index": "fixture-hash16-v1",
    "locator": "page-section-offset-v1",
    "normalization": "nul-to-replacement-warning-v1",
}
COLLECTIONS = {
    "safety-rules.json": "SAFETY_RULE",
    "alarm-codes.json": "ALARM_CODE",
    "historical-cases.json": "HISTORICAL_CASE",
    "maintenance-records.json": "MAINTENANCE_RECORD",
}


def import_manual(
    db: Session, source_path: Path | None = None, config: dict | None = None
) -> KnowledgeRelease:
    source = (source_path or PROJECT_ROOT / ".private/knowledge/apx240-manual.pdf").resolve()
    allowed = (PROJECT_ROOT / ".private/knowledge").resolve()
    if not source.is_relative_to(allowed) or not source.is_file():
        raise DomainError("INVALID_SOURCE_PATH")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = json.loads(
        (PROJECT_ROOT / "knowledge/seed/apx240-manual-manifest.json").read_text(encoding="utf-8")
    )
    if checksum != manifest["sha256"]:
        raise DomainError("SOURCE_MANIFEST_MISMATCH")
    selected_config = dict(config or CONFIG)
    seed_data = {
        name: json.loads((PROJECT_ROOT / "knowledge/seed" / name).read_text(encoding="utf-8"))
        for name in COLLECTIONS
    }
    # Seed transformations are part of the parser/index release identity too.
    release_key = content_hash([checksum, selected_config, seed_data])
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": release_key}
    )
    existing = db.scalar(
        select(KnowledgeRelease).where(KnowledgeRelease.release_key == release_key)
    )
    if existing:
        return existing
    release = KnowledgeRelease(
        release_key=release_key, source_checksum=checksum, config=selected_config
    )
    db.add(release)
    db.flush()
    document = pymupdf.open(source)
    try:
        raw_pages = [document[i].get_text() for i in range(len(document))]
    finally:
        document.close()
    records: list[tuple[str, str, str, dict[str, Any], dict[str, Any]]] = []
    for page_number, page_text in enumerate(raw_pages, 1):
        section = next(
            (line for line in page_text.splitlines() if re.match(r"\d+\. ", line)), "cover"
        )
        records.append(
            (
                f"MANUAL-P{page_number}",
                "MANUAL",
                page_text.replace("\x00", "\ufffd"),
                {"page": page_number, "section": section, "table": None},
                {
                    "extraction_warning": "UNMAPPED_GLYPH" if "\x00" in page_text else None,
                    "raw_text_sha256": hashlib.sha256(page_text.encode()).hexdigest(),
                },
            )
        )
    for name, collection in COLLECTIONS.items():
        for row in seed_data[name]:
            # Exact retained source excerpt, not an LLM summary. Validate against actual page.
            page_text = raw_pages[row["source_page"] - 1]
            quote = row["excerpt"]
            if quote not in page_text:
                raise DomainError("SOURCE_LOCATOR_MISMATCH")
            records.append(
                (
                    row["id"],
                    collection,
                    quote.replace("\x00", "\ufffd"),
                    {
                        "page": row["source_page"],
                        "section": row["source_section"],
                        "table": collection,
                        "character_start": page_text.index(quote),
                        "character_end": page_text.index(quote) + len(quote),
                    },
                    row,
                )
            )
    for key, collection, body, locator, metadata in records:
        vector = fixture_embedding(body)
        record = SourceRecord(
            release_id=release.id,
            source_key=key,
            collection=collection,
            content=body,
            locator=locator,
            checksum=hashlib.sha256(body.encode()).hexdigest(),
            metadata_fields={
                **metadata,
                "mode": "FIXTURE",
                "egress": "DENY",
                "origin": "EXAM_SOURCE",
            },
            embedding=vector,
        )
        db.add(record)
        db.flush()
        width = int(selected_config["chunk_chars"])
        if not 200 <= width <= 2000:
            raise DomainError("INVALID_CHUNK_CONFIG")
        for start in range(0, len(body), width):
            fragment = body[start : start + width]
            db.add(
                KnowledgeChunk(
                    id=content_hash([release.id, key, start, fragment]),
                    source_id=record.id,
                    text=fragment,
                    locator={
                        **locator,
                        "record_offset_start": start,
                        "record_offset_end": start + len(fragment),
                    },
                )
            )
    db.flush()
    return release
