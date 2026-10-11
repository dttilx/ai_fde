import copy
from datetime import UTC, datetime, timedelta

import pytest

from app.shared.providers.data_profile import ProcessingGrant, ProviderDataProfile
from app.shared.providers.egress import authorize_egress
from app.shared.providers.jev_payload import UNKNOWN_STATES, build_projection


def profile(endpoint="https://api.typesafe.ai/v1/systemone"):
    return ProviderDataProfile(
        "jev",
        endpoint,
        "profile-v1",
        "fixture-terms",
        datetime.now(UTC),
        True,
        ("SELF_AUTHORED_SIMULATION",),
    )


def grant(**changes):
    fields = dict(
        policy_id="policy1",
        version=1,
        origin="SELF_AUTHORED_SIMULATION",
        egress="APPROVED_REDACTED",
        providers=("jev",),
        purposes=("retrieval",),
        basis="self-authored simulation",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        readable=True,
    )
    fields.update(changes)
    return ProcessingGrant(**fields)


def payload():
    facts = {
        "alarm_code": "A101",
        "readings": [],
        "phenomena": [],
        "preheating_confirmed": None,
        "device_states": copy.deepcopy(UNKNOWN_STATES),
    }
    return build_projection(
        "jev-1.13",
        facts,
        [
            {
                "source_id": "local-private-id",
                "kind": "ALARM_CODE",
                "approved_excerpt": "Permitted self-authored technical example.",
            }
        ],
        ("applicability",),
    )[0]


def test_denied_contributor_stays_denied_after_masking():
    result = authorize_egress(
        (grant(), grant(policy_id="second", egress="DENY")), profile(), "retrieval", payload()
    )
    assert result.decision == "SKIPPED_POLICY"
    assert result.input_hash is None


@pytest.mark.parametrize(
    "changes",
    [
        {"basis": None},
        {"readable": False},
        {"providers": ()},
        {"purposes": ()},
        {"origin": "EXAM_SOURCE"},
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
    ],
)
def test_missing_or_expired_basis_blocks(changes):
    assert (
        authorize_egress((grant(**changes),), profile(), "retrieval", payload()).decision
        == "SKIPPED_POLICY"
    )


def test_approved_projection_and_receipt_have_no_source_identity():
    value = payload()
    assert "local-private-id" not in str(value)
    result = authorize_egress((grant(),), profile(), "retrieval", value)
    assert result.decision == "ALLOWED"
    assert result.input_hash
    assert not hasattr(result, "payload")


def test_proxy_and_raw_fields_blocked():
    assert (
        authorize_egress(
            (grant(),), profile("https://proxy.example/v1/systemone"), "retrieval", payload()
        ).decision
        == "SKIPPED_POLICY"
    )
    value = payload()
    value["state"]["serial_number"] = "private"
    assert authorize_egress((grant(),), profile(), "retrieval", value).decision == "SKIPPED_POLICY"


def test_residual_sensitive_and_question_injection_rejected():
    value = payload()
    value["state"]["sources"][0]["excerpt"] = "WO-240-042 contact https://private.example"
    assert (
        authorize_egress((grant(),), profile(), "retrieval", value).reason == "RESIDUAL_SENSITIVE"
    )
    value = payload()
    value["questions"]["applicability"]["instructions"] += " leaked data"
    assert authorize_egress((grant(),), profile(), "retrieval", value).decision == "SKIPPED_POLICY"
