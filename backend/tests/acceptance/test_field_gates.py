"""Private field gates fail closed when live infrastructure is absent."""

import os
import subprocess
import sys

from app.shared.config import PROJECT_ROOT


def test_field_evaluation_gate_is_blocked_without_real_provider():
    env = {key: value for key, value in os.environ.items() if key != "PROVIDER_MODE"}
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/evaluate_field_demo.py")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and '"status": "BLOCKED"' in result.stdout
