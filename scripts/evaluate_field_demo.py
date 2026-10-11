"""Produce a truthful field-evaluation gate; unavailable live conditions stay BLOCKED."""

import json
import os
from pathlib import Path


def main() -> int:
    live = os.environ.get("PROVIDER_MODE") == "REAL_APPROVED_EXTERNAL"
    result = {
        "status": "BLOCKED",
        "reason": "MEASURED_MODEL_AND_HARDWARE_RESULTS_REQUIRED" if live else "REAL_PROVIDER_OR_FIELD_HARDWARE_NOT_AVAILABLE",
        "fixture_regression": "357 backend tests and 20 frontend tests are recorded separately",
        "targets": {"text_active_seconds": 30, "media_seconds": 60, "page_seconds": 2},
    }
    Path(".private/field-evaluation-result.json").parent.mkdir(parents=True, exist_ok=True)
    Path(".private/field-evaluation-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
