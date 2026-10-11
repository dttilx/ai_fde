"""Generate clearly synthetic media; never label fixture recognition as real OCR/VLM."""

import hashlib
import json
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / "knowledge/fixtures/media"
directory.mkdir(parents=True, exist_ok=True)
image = Image.new("RGB", (420, 140), "white")
draw = ImageDraw.Draw(image)
draw.text((20, 15), "SYNTHETIC FIXTURE - NOT A REAL DEVICE", fill="black")
draw.text((20, 50), "A203  SET 165 C  ACTUAL 128 C  CURRENT 0 A", fill="black")
path = directory / "a203-panel-fixture.png"
image.save(path)
candidates = [{"key": key, "value": value, "confidence": None,
               "locator": {"region": [20, 45, 400, 70]},
               "limitation": "注册合成fixture候选，不代表真实OCR准确率。"}
              for key, value in {"alarm_code": "A203", "set_temperature_c": 165,
                                 "actual_temperature_c": 128, "heating_current_a": 0}.items()]
manifest = [{"checksum": hashlib.sha256(path.read_bytes()).hexdigest(),
             "origin": "SELF_AUTHORED_SIMULATION", "ocr": candidates, "vision": []}]
(ROOT / "knowledge/seed/media-fixtures.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
for index, item in enumerate(json.loads((ROOT / "knowledge/seed/qr-fixtures.json").read_text(encoding="utf-8"))):
    qrcode.make(item["qr"]).save(directory / f"qr-{index}.png")
print("Generated 1 synthetic panel and 4 QR assets; all explicitly fixture-labelled.")
