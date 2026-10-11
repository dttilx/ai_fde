"""Contract checks use the fixture provider and do not assert live model quality."""

import json

from jsonschema import Draft202012Validator

from app.shared.config import PROJECT_ROOT
from tests.acceptance.test_a203 import create


def schema(name):
    return json.loads(
        (PROJECT_ROOT / "specs/001-apx240-multimodal-diagnosis/contracts" / name).read_text(
            encoding="utf-8"
        )
    )


def test_a203_report_matches_v4_and_citation_bearing_sections():
    client, started = create()
    report = client.get(f"/api/diagnoses/{started['diagnosis_run_id']}").json()["report"]
    errors = list(Draft202012Validator(schema("diagnosis-report.schema.json")).iter_errors(report))
    assert errors == []
    references = {item["citation_id"] for item in report["evidence_sources"]}
    for section in ("possible_causes", "safety_preconditions", "check_sequence"):
        assert all(set(item["citation_ids"]).issubset(references) for item in report[section])


def test_job_and_graph_contracts_reject_unknown_states():
    job_contract = schema("job-status.schema.json")
    graph_contract = schema("graph-state.schema.json")
    assert "QUEUED" in job_contract["properties"]["status"]["enum"]
    assert "WAITING_EXPERT" in graph_contract["properties"]["state"]["enum"]
    assert list(Draft202012Validator(job_contract).iter_errors({"status": "BROKEN"}))
    assert list(Draft202012Validator(graph_contract).iter_errors({"state": "BROKEN"}))


def test_runtime_job_graph_retrieval_and_citation_payloads_match_contracts():
    client, started = create()
    run_id = started["diagnosis_run_id"]
    checkpoint = client.get(f"/api/diagnoses/{run_id}/checkpoint").json()
    retrieval = client.get(f"/api/diagnoses/{run_id}/retrieval-assessments").json()
    citations = client.get(f"/api/diagnoses/{run_id}/citation-assessments").json()
    job = client.get(f"/api/jobs/{started['job_id']}").json()
    cases = [
        ("graph-state.schema.json", checkpoint),
        ("retrieval-assessment.schema.json", retrieval),
        ("citation-assessment.schema.json", citations),
        ("job-status.schema.json", job),
    ]
    for name, payload in cases:
        errors = list(Draft202012Validator(schema(name)).iter_errors(payload))
        assert errors == [], (name, errors)
