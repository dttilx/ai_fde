"""Bounded perception yields candidates, never confirmed facts."""

import asyncio
from typing import Any

from sqlalchemy import func, select

from app.access.models import User
from app.evidence.ocr import FixtureOCR, LocalOCR
from app.evidence.qr import decode_qr, resolve_qr
from app.evidence.service import accessible_media
from app.evidence.video import decode_video
from app.evidence.vision import FixtureVision
from app.incidents.models import Evidence, Incident
from app.shared.auth_context import ActorContext
from app.shared.config import settings
from app.shared.db import require_record, session_factory
from app.shared.errors import DomainError
from app.shared.invocations import assert_fence
from app.shared.jobs.executor import ExecutionResult
from app.shared.storage import storage


def context(db, ticket):
    assert_fence(db, ticket.job_id, ticket.fence)
    user = require_record(db, User, ticket.actor_id)
    if not user.enabled or user.auth_version != ticket.payload["actor_version"]:
        raise DomainError("MEDIA_ACTOR_REVOKED", 403)
    actor = ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)
    actor.require_role("FIELD_ENGINEER", "EXPERT")
    return actor, accessible_media(db, actor, ticket.payload["media_id"])


def process_sync(ticket, *, ocr=None, vision=None):
    with session_factory()() as db, db.begin():
        actor, media = context(db, ticket)
        if media.processing_status in {"CANDIDATES_READY", "UNUSABLE"}:
            return ExecutionResult(
                "COMPLETED",
                {
                    "media_id": media.id,
                    "recognition_status": "CANDIDATES"
                    if media.processing_status == "CANDIDATES_READY"
                    else "UNAVAILABLE",
                    "processing_status": media.processing_status,
                },
            )
        key, media_type, content_type = media.storage_ref, media.media_type, media.content_type
        media.processing_status = "PROCESSING"
    data = storage().get(key)
    if settings().provider_mode != "FIXTURE" and (ocr is None or vision is None):
        raise DomainError("REAL_MEDIA_PROVIDER_NOT_CONFIGURED", 409)
    outputs: list[tuple[str, dict[str, Any]]] = []
    frames: list[dict[str, Any]] = []
    if media_type == "IMAGE":
        outputs.extend(
            (source, adapter.analyze(data))
            for source, adapter in (
                (
                    "OCR",
                    ocr or (LocalOCR() if settings().ocr_provider == "rapidocr" else FixtureOCR()),
                ),
                ("VISION", vision or FixtureVision()),
            )
        )
        qr = decode_qr(data)
    else:
        decoded = decode_video(data, content_type, frames=True)
        for frame in decoded["frames"]:
            stored = storage().put(frame["bytes"], "image/png")
            frames.append(
                {
                    "index": frame["index"],
                    "timestamp_ms": frame["timestamp_ms"],
                    "storage_ref": stored.key,
                }
            )
            outputs.append(
                (
                    f"VIDEO{frame['index']}",
                    {
                        "mode": "REAL_LOCAL",
                        "model": "opencv-bounded-keyframes-v1",
                        "candidates": [],
                        "locator": {
                            "timestamp_ms": frame["timestamp_ms"],
                            "frame_index": frame["index"],
                        },
                        "limitation": "关键帧过暗，无法判断现场现象。"
                        if frame["dark"]
                        else "已提取关键帧；未配置视觉分析，无法判断故障现象。"
                        "声音需人工提供带时间的观察。",
                    },
                )
            )
        qr = {"candidate": None, "limitation": None}
    with session_factory()() as db, db.begin():
        actor, media = context(db, ticket)
        db.get(Incident, media.incident_id, with_for_update=True)
        candidate_count = 0
        if qr["candidate"]:
            qr = resolve_qr(db, actor, qr["candidate"])
        if media_type == "IMAGE":
            outputs.append(
                (
                    "QR",
                    {
                        "mode": "REAL_LOCAL",
                        "model": "opencv-qr-v1",
                        "candidates": [qr["candidate"]] if qr["candidate"] else [],
                        "limitation": qr["limitation"],
                    },
                )
            )
        for source, result in outputs:
            entries = result["candidates"] or [
                {"key": f"{source}:{media.id}", "value": None, "limitation": result["limitation"]}
            ]
            for item in entries:
                recognized = bool(result["candidates"])
                candidate_count += int(recognized)
                version = (
                    db.scalar(
                        select(func.max(Evidence.version)).where(
                            Evidence.incident_id == media.incident_id,
                            Evidence.evidence_key == item["key"],
                        )
                    )
                    or 0
                ) + 1
                value = {
                    "value": item["value"],
                    "confidence": item.get("confidence"),
                    "limitation": item.get("limitation", result.get("limitation")),
                }
                if item.get("asset_context"):
                    value["asset_context"] = item["asset_context"]
                db.add(
                    Evidence(
                        incident_id=media.incident_id,
                        media_id=media.id,
                        evidence_key=item["key"],
                        version=version,
                        state="CANDIDATE" if recognized else "UNAVAILABLE",
                        source=source,
                        reviewer_id=None,
                        value=value,
                        locators=item.get("locator", result.get("locator", {})),
                        provenance={
                            "mode": result["mode"],
                            "model": result["model"],
                            "job_id": ticket.job_id,
                        },
                    )
                )
                db.flush()
                from app.evidence.policy import bind_evidence_policy

                bind_evidence_policy(
                    db,
                    db.scalar(
                        select(Evidence).where(
                            Evidence.incident_id == media.incident_id,
                            Evidence.evidence_key == item["key"],
                            Evidence.version == version,
                        )
                    ),
                    media.id,
                )
        media.processing_status = "CANDIDATES_READY" if candidate_count else "UNUSABLE"
        return ExecutionResult(
            "COMPLETED",
            {
                "media_id": media.id,
                "candidate_count": candidate_count,
                "processing_status": media.processing_status,
                "recognition_status": "CANDIDATES" if candidate_count else "UNAVAILABLE",
                "frames": frames,
                "processing_mode": "REAL_LOCAL"
                if media_type == "VIDEO" or settings().ocr_provider == "rapidocr"
                else "FIXTURE",
            },
        )


async def process_media(ticket):
    return await asyncio.to_thread(process_with_failure, ticket)


def process_with_failure(ticket):
    try:
        return process_sync(ticket)
    except Exception as exc:
        code = exc.code if isinstance(exc, DomainError) else "MEDIA_PROCESSING_FAILED"
        try:
            with session_factory()() as db, db.begin():
                actor, media = context(db, ticket)
                media.processing_status = "FAILED"
                version = (
                    db.scalar(
                        select(func.max(Evidence.version)).where(
                            Evidence.incident_id == media.incident_id,
                            Evidence.evidence_key == f"processing:{media.id}",
                        )
                    )
                    or 0
                ) + 1
                db.add(
                    Evidence(
                        incident_id=media.incident_id,
                        media_id=media.id,
                        evidence_key=f"processing:{media.id}",
                        version=version,
                        state="UNAVAILABLE",
                        source="PROCESSING",
                        reviewer_id=None,
                        value={"value": None, "limitation": code},
                        locators={},
                        provenance={"mode": "NOT_CALLED", "model": None, "job_id": ticket.job_id},
                    )
                )
        except DomainError as current_error:
            if current_error.code not in {"INVOCATION_FENCED", "MEDIA_ACTOR_REVOKED", "NOT_FOUND"}:
                raise
        raise
