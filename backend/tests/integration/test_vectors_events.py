from uuid import uuid4

import pytest
from sqlalchemy import select

from app.access.models import User
from app.access.resource_policy import authorized_source_ids
from app.diagnosis.events import authorized_events, emit
from app.diagnosis.models import DiagnosisRun
from app.knowledge.retrieval import retrieve
from app.knowledge.vectors import add_vectors, ranked_vectors
from app.shared.auth_context import ActorContext
from app.shared.db import session_factory
from app.shared.errors import DomainError
from app.shared.providers.protocols import ProviderResult
from tests.acceptance.test_a203 import create, execute
from tests.acceptance.test_diagnosis_controls import review_request


def actor(db, name):
    user = db.scalar(select(User).where(User.username == name))
    return ActorContext(user.id, user.organization_id, tuple(user.roles), user.auth_version)


def test_actual_pgvector_model_index_and_scope_isolation_with_keyword_fallback():
    with session_factory()() as db:
        engineer = actor(db, "engineer")
        scope = authorized_source_ids(db, engineer)
        version = uuid4().hex
        result = ProviderResult(
            "REAL_LOCAL",
            "transport-test-v1",
            "SUCCEEDED",
            {"vectors": [[1.0, 0.0], [0.0, 1.0]], "dimensions": 2},
        )
        add_vectors(db, engineer, scope[:2], result, version)
        ranked = ranked_vectors(db, scope, [1.0, 0.0], result.model, version)
        assert [r.id for r in ranked] == scope[:2]
        assert ranked_vectors(db, scope[1:2], [1.0, 0.0], result.model, version)[0].id == scope[1]
        assert ranked_vectors(db, scope, [1.0, 0.0], "other-model", version) == []
        assert ranked_vectors(db, scope, [1.0, 0.0], result.model, "wrong-version") == []
        rows = retrieve(
            db,
            engineer,
            "A203",
            "A203 电流",
            scope,
            query_vector=[1.0, 0.0],
            vector_model="unavailable",
            index_version=version,
        )
        assert {"A203", "SAFE-01", "H02"} <= {r["source_key"] for r in rows}
        assert {r["embedding_mode"] for r in rows} == {"KEYWORD_ONLY"}
        # Entire synthetic vector transaction is rolled back on context exit.


def test_graph_events_resume_order_cursor_and_effect_idempotency():
    client, started = create(force=True)
    run_id = started["diagnosis_run_id"]
    with session_factory()() as db:
        run = db.get(DiagnosisRun, run_id)
        incident_id = run.incident_id
        events = authorized_events(db, actor(db, "engineer"), incident_id)
        assert events[-1]["type"] == "graph.interrupted"
        cursor = events[-1]["event_id"]
        assert authorized_events(db, actor(db, "engineer"), incident_id, cursor) == []
        with pytest.raises(DomainError, match="NOT_FOUND"):
            authorized_events(db, actor(db, "expert"), incident_id)
    response = client.post(f"/api/diagnoses/{run_id}/resume", json=review_request(client, run_id))
    assert response.status_code == 200, response.text
    execute(response.json()["job_id"])
    with session_factory()() as db:
        new = authorized_events(db, actor(db, "engineer"), incident_id, cursor)
        assert new[0]["type"] == "graph.resumed"
        assert new[-1]["type"] == "diagnosis.report_ready"
        assert [e["sequence"] for e in new] == sorted(set(e["sequence"] for e in new))
        run = db.get(DiagnosisRun, run_id)
        first = emit(db, run, "graph.resumed", "test:" + run_id, {"state": "PREPARING"})
        again = emit(db, run, "graph.resumed", "test:" + run_id, {"state": "ignored"})
        assert first.id == again.id and again.payload == {"state": "PREPARING"}
