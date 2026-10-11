"""Run real pytest assertions against deliberate defects in isolated child processes.

No application/test files are modified. Mutant test failures are expected only here;
ordinary pytest must still fail on any failed assertion. This is not a quality score
for models or a claim of exhaustive mutation coverage.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TARGETS = [
    "tests/unit/test_template_support.py",
    "tests/unit/test_release_policy.py",
    "tests/unit/test_fixtures.py",
]
REGISTRY_TARGETS = ["tests/integration/test_template_registry.py"]
RETRIEVAL_TARGETS = ["tests/integration/test_retrieval_routes.py"]
JEV_TARGETS = ["tests/unit/test_jev_stage.py", "tests/acceptance/test_retrieval_assessment.py"]
CLAIM_TARGETS = ["tests/unit/test_claim_provenance.py", "tests/acceptance/test_claim_integrity.py"]
SUPPORT_TARGETS = ["tests/integration/test_claim_support.py"]
CHILD = r"""
import json
import sys
import pytest

name = sys.argv[1]
if name == "always_valid_template":
    import app.knowledge.templates as module
    module.a203_support = lambda *a, **k: module.TemplateSupport(True, "bad-mutant", ())
elif name == "always_auto_release":
    import app.diagnosis.release_policy as module
    module.release_mode = lambda *a, **k: "AUTO_VALIDATED"
elif name == "swallow_provider_failure":
    from app.shared.providers.fixtures import FixtureProvider
    original = FixtureProvider.invoke
    async def swallow(self, payload):
        return await original(self, {**payload, "fixture_failure": False})
    FixtureProvider.invoke = swallow
elif name == "bypass_template_registry":
    import app.knowledge.template_registry as module
    module.registered_support = lambda db, facts, qualified, cites, contradictions=(): (
        module.TemplateSupport(
            True, module.stage_template(db, cites[0]["knowledge_release_id"]).id, ()
        )
    )
elif name == "ignore_citation_lineage":
    import app.diagnosis.retrieval_context as module
    module.citations = lambda *a, **k: []
elif name == "fold_required_sources":
    import app.knowledge.passage_assessment as module
    module.route = lambda *a, **k: "FOLDED"
elif name == "bypass_claim_review_binding":
    import app.diagnosis.claim_review as module
    module.accepted_reviews = lambda *a, **k: True
elif name == "disable_auto_repair":
    import app.diagnosis.auto_repair as module
    module.repair_once = lambda *a, **k: None
elif name == "bypass_claim_processing_permission":
    import app.diagnosis.claim_support as module
    from app.shared.providers.egress import EgressReceipt
    module.authorize_egress = lambda grants, profile, purpose, payload: EgressReceipt(
        "ALLOWED" if payload else "SKIPPED_POLICY",
        "APPROVED_MINIMAL_PROJECTION" if payload else "JEV_PROJECTION_INVALID",
        profile.provider, (), "mutant" if payload else None, profile.version,
    )
elif name not in {
    "baseline", "baseline_registry", "baseline_retrieval", "baseline_jev", "baseline_claims",
    "baseline_support"
}:
    raise ValueError("Unknown mutation")

class Tracker:
    collected = 0
    failed_calls = 0
    passed_calls = 0
    infrastructure_errors = 0
    def pytest_collection_finish(self, session):
        self.collected = len(session.items)
    def pytest_collectreport(self, report):
        if report.failed:
            self.infrastructure_errors += 1
    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.failed_calls += int(report.failed)
            self.passed_calls += int(report.passed)
        elif report.failed:
            self.infrastructure_errors += 1

tracker = Tracker()
code = int(pytest.main([*sys.argv[2:], "-q", "--tb=no"], plugins=[tracker]))
print("APX_SENSITIVITY=" + json.dumps({"mode": name, "exit_code": code,
    "collected": tracker.collected, "failed_calls": tracker.failed_calls,
    "passed_calls": tracker.passed_calls, "infrastructure_errors": tracker.infrastructure_errors}))
sys.exit(code)
"""


def main() -> int:
    if sys.argv[1:] not in ([], ["--claims-only"], ["--support-only"]):
        raise ValueError("Supported options: --claims-only, --support-only")
    claims_only = sys.argv[1:] == ["--claims-only"]
    support_only = sys.argv[1:] == ["--support-only"]
    results = []
    for name in (
        "baseline",
        "always_valid_template",
        "always_auto_release",
        "swallow_provider_failure",
        "baseline_registry",
        "bypass_template_registry",
        "baseline_retrieval",
        "ignore_citation_lineage",
        "baseline_jev",
        "fold_required_sources",
        "baseline_claims",
        "bypass_claim_review_binding",
        "baseline_support",
        "disable_auto_repair",
        "bypass_claim_processing_permission",
    ):
        if claims_only and name not in {"baseline_claims", "bypass_claim_review_binding"}:
            continue
        if support_only and name not in {
            "baseline_support", "disable_auto_repair", "bypass_claim_processing_permission"
        }:
            continue
        if name in {"baseline_support", "disable_auto_repair", "bypass_claim_processing_permission"}:
            targets = SUPPORT_TARGETS
        elif name in {"baseline_claims", "bypass_claim_review_binding"}:
            targets = CLAIM_TARGETS
        elif name in {"baseline_registry", "bypass_template_registry"}:
            targets = REGISTRY_TARGETS
        elif name in {"baseline_retrieval", "ignore_citation_lineage"}:
            targets = RETRIEVAL_TARGETS
        elif name in {"baseline_jev", "fold_required_sources"}:
            targets = JEV_TARGETS
        else:
            targets = TARGETS
        completed = subprocess.run(
            [sys.executable, "-c", CHILD, name, *targets],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90 if targets == SUPPORT_TARGETS else 45,
        )
        markers = [
            line for line in completed.stdout.splitlines() if line.startswith("APX_SENSITIVITY=")
        ]
        if len(markers) != 1:
            print(json.dumps({"mode": name, "status": "HARNESS_ERROR"}))
            return 1
        result = json.loads(markers[0].split("=", 1)[1])
        valid_execution = result["collected"] > 0 and result["infrastructure_errors"] == 0
        expected = (
            (
                completed.returncode == 0
                and result["failed_calls"] == 0
                and result["passed_calls"] == result["collected"]
            )
            if name.startswith("baseline")
            else (completed.returncode == 1 and result["failed_calls"] > 0)
        )
        result["status"] = "BASELINE_PASS" if name.startswith("baseline") else "DEFECT_DETECTED"
        if not valid_execution or not expected:
            result["status"] = "SENSITIVITY_FAILED"
            print(json.dumps(result))
            return 1
        results.append(result)
        print(json.dumps(result))
    output = ROOT / ".private" / "test-audit" / (
        "support-sensitivity.json" if support_only
        else "claims-sensitivity.json" if claims_only else "sensitivity.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
