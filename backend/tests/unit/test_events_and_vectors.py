import pytest

from app.diagnosis.events import encode_sse
from app.knowledge.vectors import add_vectors, valid_vector
from app.shared.errors import DomainError
from app.shared.providers.protocols import ProviderResult


def test_sse_has_stable_id_and_json_payload_without_reasoning():
    rendered = encode_sse(
        {
            "event_id": "e1",
            "type": "graph.interrupted",
            "incident_id": "i1",
            "sequence": 4,
            "occurred_at": "now",
            "trace_id": "r1",
            "payload": {"state": "WAITING_EXPERT"},
        }
    )
    assert rendered.startswith("id: e1\nevent: graph.interrupted\n")
    assert '"state": "WAITING_EXPERT"' in rendered and "chain_of_thought" not in rendered


def test_real_vector_validation_rejects_nan_zero_and_non_numeric_values():
    assert valid_vector([1.0, 0.0])
    assert not valid_vector([0.0, 0.0])
    assert not valid_vector([float("nan"), 1.0])
    assert not valid_vector([True, 1.0])


def test_fixture_embedding_result_cannot_be_stored_as_real_vector():
    result = ProviderResult("FIXTURE", "fixture-hash16-v1", "FIXTURE", {"vectors": [[1, 0]]})
    with pytest.raises(DomainError, match="REAL_VECTOR_RESULT_REQUIRED"):
        add_vectors(None, None, ["x"], result, "v1")
