import re

from app.incidents.assets import asset_summary
from app.shared.errors import DomainError


def decode_qr(data: bytes) -> dict:
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return {"candidate": None, "limitation": "图片无法解码。"}
    detector = cv2.QRCodeDetector()
    success, decoded, points, _ = detector.detectAndDecodeMulti(image)
    values = sorted({value for value in decoded if value}) if success else []
    if not values and (points is None or len(points) <= 1):
        # Some single-code layouts are missed by the multi detector. This still
        # uses actual pixel decoding, never fixture lookup or expected-text fallback.
        decoded_single, _, _ = detector.detectAndDecode(image)
        if decoded_single:
            values = [decoded_single]
    if len(values) != 1:
        return {"candidate": None, "limitation": "未识别到唯一QR码（模糊、遮挡、缺失或多个编码）。"}
    match = re.fullmatch(r"apx240://asset/([A-Za-z0-9_-]{1,100})", values[0])
    if not match:
        return {"candidate": None, "limitation": "QR不是支持的设备编码；不访问编码中的外部链接。"}
    return {
        "candidate": {
            "key": "asset_association",
            "value": match.group(1),
            "confidence": None,
            "locator": {"qr": True},
        },
        "limitation": None,
    }


def resolve_qr(db, actor, candidate) -> dict:
    try:
        summary = asset_summary(db, actor, candidate["value"])
    except DomainError as exc:
        if exc.status == 404:
            return {"candidate": None, "limitation": "设备未知或不可访问，无法绑定。"}
        raise
    if summary["model"] != "APX-240":
        return {"candidate": None, "limitation": "设备型号不是APX-240，不能用于本项目诊断。"}
    return {"candidate": {**candidate, "asset_context": summary}, "limitation": None}
