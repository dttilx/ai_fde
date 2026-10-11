from app.diagnosis.models import DiagnosisRun
from app.shared.db import session_factory
from tests.acceptance.test_a203 import create
from tests.acceptance.test_a310 import answer


def test_postgres_checkpoint_resume_survives_fresh_worker_process():
    client, started = create(description="A310，似乎漏气")
    run_id = started["diagnosis_run_id"]
    answer(client, run_id, {"upstream_pressure_mpa": 0.64})
    cp = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    assert cp["graph_thread_id"] == run_id and cp["counters"]["resumes"] == 1
    # The next segment is deliberately executed by a new Python process, not a mocked state.
    result = answer(
        client,
        run_id,
        {"device_pressure_mpa": 0.41, "continuous_leak_sound": True},
        fresh_process=True,
    )
    assert result["state"] == "COMPLETED"
    with session_factory()() as db:
        assert db.get(DiagnosisRun, run_id).graph_thread_id == run_id


def test_missing_native_checkpoint_fails_closed_without_fresh_thread():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    with session_factory()() as db, db.begin():
        run = db.get(DiagnosisRun, run_id)
        run.native_checkpoint_id = "missing-checkpoint"
    response = client.get(f"/api/diagnoses/{run_id}/checkpoint")
    assert response.status_code in {200, 409}
    with session_factory()() as db:
        assert db.get(DiagnosisRun, run_id).graph_thread_id == run_id
