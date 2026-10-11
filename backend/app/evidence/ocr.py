"""Swappable OCR protocol; fixture expectations apply only to registered media checksums."""

import json
import re
from functools import lru_cache
from threading import Lock
from typing import Protocol

from app.shared.config import PROJECT_ROOT
from app.shared.storage import digest


class CandidateAdapter(Protocol):
    def analyze(self, data: bytes) -> dict: ...


def fixture_candidates(data, capability):
    path = PROJECT_ROOT / "knowledge/seed/media-fixtures.json"
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    matched = next(
        (
            row
            for row in records
            if row["checksum"] == digest(data) and row.get("origin") == "SELF_AUTHORED_SIMULATION"
        ),
        None,
    )
    return matched.get(capability, []) if matched else []


class FixtureOCR:
    def analyze(self, data: bytes) -> dict:
        return {
            "mode": "FIXTURE",
            "model": "fixture-ocr-checksum-v1",
            "candidates": fixture_candidates(data, "ocr"),
            "limitation": "仅校验已注册的合成媒体fixture；任意上传图片没有OCR识别保证。",
        }


@lru_cache(maxsize=1)
def local_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)


OCR_LOCK = Lock()


class LocalOCR:
    """Pixel-based local recognition. No expected-result or fixture fallback."""

    def analyze(self, data: bytes) -> dict:
        from app.diagnosis.normalization import normalize
        from app.incidents.schemas import IncidentInput

        with OCR_LOCK:
            rows, _ = local_engine()(data)
        candidates, transcript = [], []
        for box, text, score in (rows or [])[:80]:
            if float(score) < 0.6:
                continue
            text = str(text).strip()
            transcript.append(text)
            normalized = re.sub(r"[:：=]", " ", text)
            facts, _, conflicts, _ = normalize(IncidentInput(raw_description=normalized))
            for key, value in facts.items():
                if key in conflicts:
                    continue
                candidates.append(
                    {
                        "key": key,
                        "value": value,
                        "confidence": float(score),
                        "locator": {"region": box, "recognized_text": text},
                    }
                )
        if transcript:
            # The APX-240 panel fixture prints English labels.  Normalize these
            # pixel-recognized labels into the same structured facts used by
            # text reports; values remain CANDIDATE until a person reviews them.
            combined = " ".join(transcript)
            patterns = {
                "set_temperature_c": r"(?:SET|设定温度)\s*[:=]?\s*(\d+(?:\.\d+)?)",
                "actual_temperature_c": r"(?:ACTUAL|实际温度)\s*[:=]?\s*(\d+(?:\.\d+)?)",
                "heating_current_a": r"(?:CURRENT|加热电流)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            }
            for key, pattern in patterns.items():
                match = re.search(pattern, combined, flags=re.IGNORECASE)
                if match:
                    candidates.append(
                        {
                            "key": key,
                            "value": float(match.group(1)),
                            "confidence": 0.9,
                            "locator": {"region": "full_image", "recognized_text": combined},
                        }
                    )
            candidates.append(
                {
                    "key": "ocr_text",
                    "value": "\n".join(transcript)[:5000],
                    "confidence": None,
                    "locator": {"region": "full_image"},
                }
            )
        return {
            "mode": "REAL_LOCAL",
            "model": "rapidocr-onnxruntime-1.4.4",
            "candidates": candidates[:19],
            "limitation": (None if candidates else "未检测到可识别文字；可能模糊、过小或无文字。"),
        }
