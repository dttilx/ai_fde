"""Live Jev gate: missing authorization is a blocked result, never fixture success."""

import os
import subprocess
import sys

from app.shared.config import PROJECT_ROOT


def test_live_jev_without_explicit_profile_is_blocked():
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"JEV_API_KEY", "PROVIDER_MODE"}
    }
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/evaluate_jev.py")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert '"status": "BLOCKED"' in result.stdout
    assert "API_KEY" not in result.stdout
