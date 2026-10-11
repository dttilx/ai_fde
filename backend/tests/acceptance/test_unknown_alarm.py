import pytest

from tests.acceptance.test_a203 import create


@pytest.mark.parametrize("description", ["A999，设备异常", "无法读清报警码，请帮忙判断"])
def test_unknown_alarm_does_not_reuse_a203_template_or_invent_cause(description):
    client, started = create(description=description)
    run = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()
    assert run["state"] == "WAITING_EXPERT", run
    assert run["report"] is None
    checkpoint = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}/checkpoint").json()
    assert checkpoint["interrupt_type"] == "EXPERT"
    assert "finalize" not in [row["node"] for row in run["timeline"]]
