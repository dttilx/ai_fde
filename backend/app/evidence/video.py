"""Local decoder runs in a killable subprocess. No automatic audio or fault inference."""

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.evidence.schemas import DECODE_SECONDS, IMAGE_PIXELS, VIDEO_FRAMES, VIDEO_SECONDS
from app.shared.errors import DomainError


def decode_video(data, content_type, frames=False):
    if not (
        (content_type == "video/mp4" and data[4:8] == b"ftyp")
        or (content_type == "video/webm" and data[:4] == b"\x1aE\xdf\xa3")
    ):
        raise DomainError("MEDIA_TYPE_MISMATCH", 422)
    with tempfile.TemporaryDirectory(prefix="apx_video_") as directory:
        folder = Path(directory)
        path = folder / ("input.mp4" if content_type == "video/mp4" else "input.webm")
        path.write_bytes(data)
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.evidence.video",
                    str(path),
                    str(folder),
                    "frames" if frames else "probe",
                ],
                capture_output=True,
                timeout=DECODE_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise DomainError("VIDEO_DECODE_TIMEOUT", 422) from None
        if result.returncode != 0:
            raise DomainError("MEDIA_DECODE_FAILED", 422)
        try:
            metadata = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise DomainError("MEDIA_DECODE_FAILED", 422) from None
        if metadata.get("error"):
            raise DomainError(metadata["error"], 413 if metadata["error"] == "VIDEO_LIMIT" else 422)
        if frames:
            for frame in metadata["frames"]:
                frame["bytes"] = (folder / f"frame-{frame['index']}.png").read_bytes()
        return metadata


def _decode(path, folder, frames):
    import cv2

    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        width, height = (
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        if not capture.isOpened() or not all(
            math.isfinite(v) and v > 0 for v in (fps, count, width, height)
        ):
            return {"error": "MEDIA_DECODE_FAILED"}
        seconds = count / fps
        if seconds > VIDEO_SECONDS or width * height > IMAGE_PIXELS:
            return {"error": "VIDEO_LIMIT"}
        result: dict[str, Any] = {
            "width": width,
            "height": height,
            "duration_ms": round(seconds * 1000),
            "frames": [],
        }
        samples = min(VIDEO_FRAMES, int(count)) if frames else 1
        for index in range(samples):
            number = round(index * (count - 1) / max(1, samples - 1))
            capture.set(cv2.CAP_PROP_POS_FRAMES, number)
            ok, frame = capture.read()
            if not ok or frame is None:
                return {"error": "MEDIA_DECODE_FAILED"}
            if frames:
                brightness = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
                scale = min(1, 1280 / max(frame.shape[:2]))
                if scale < 1:
                    frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
                if not cv2.imwrite(str(folder / f"frame-{index}.png"), frame):
                    return {"error": "MEDIA_DECODE_FAILED"}
                result["frames"].append(
                    {
                        "index": index,
                        "timestamp_ms": round(number / fps * 1000),
                        "dark": brightness < 8,
                    }
                )
        return result
    finally:
        capture.release()


if __name__ == "__main__":
    try:
        print(json.dumps(_decode(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "frames")))
    except Exception:
        # Decoder errors are explicit failure, never a candidate or successful analysis.
        print(json.dumps({"error": "MEDIA_DECODE_FAILED"}))
