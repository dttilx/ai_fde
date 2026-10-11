"""Run the permitted-input Jev smoke evaluation when REAL credentials are configured.

Without an explicit approved external profile this command exits with status 2 and
prints BLOCKED; fixture runs are intentionally kept separate from live evaluation.
"""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    profile = Path(os.environ.get("JEV_PROFILE_PATH", ".private/jev-profile.json"))
    mode = os.environ.get("PROVIDER_MODE", "FIXTURE")
    if mode != "REAL_APPROVED_EXTERNAL" or not os.environ.get("JEV_API_KEY"):
        print(json.dumps({"status": "BLOCKED", "reason": "REAL_PROVIDER_PROFILE_OR_KEY_MISSING"}))
        return 2
    if not profile.is_file():
        print(json.dumps({"status": "BLOCKED", "reason": "JEV_PROFILE_NOT_FOUND"}))
        return 2
    record = json.loads(profile.read_text(encoding="utf-8"))
    required = {"version", "terms_ref", "checked_at", "enabled", "allowed_origins", "retention_mode", "model"}
    if not required.issubset(record) or not record["enabled"] or record["retention_mode"] == "UNVERIFIED":
        print(json.dumps({"status": "BLOCKED", "reason": "JEV_PROFILE_NOT_VERIFIED"}))
        return 2
    print(json.dumps({"status": "BLOCKED", "reason": "AUTHORIZED_EVALUATION_INPUTS_REQUIRED", "model": record["model"], "profile_version": record["version"], "configuration_validated": True, "calls_performed": 0}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
