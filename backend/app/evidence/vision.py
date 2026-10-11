from app.evidence.ocr import CandidateAdapter as CandidateAdapter
from app.evidence.ocr import fixture_candidates


class FixtureVision:
    def analyze(self, data: bytes) -> dict:
        return {
            "mode": "FIXTURE",
            "model": "fixture-vision-unavailable-v1",
            "candidates": fixture_candidates(data, "vision"),
            "limitation": "未配置真实视觉模型，无法确认现场图像现象；不推断内部故障。",
        }
