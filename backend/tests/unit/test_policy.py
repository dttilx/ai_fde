from app.access.models import PolicyBinding
from app.access.policy import derive_policy


def test_derived_scope_is_intersection_and_denial_survives_masking():
    first = PolicyBinding(
        id="one", readable_by=["engineer", "expert"], egress="APPROVED_REDACTED", basis="approved"
    )
    second = PolicyBinding(id="two", readable_by=["expert"], egress="DENY")
    result = derive_policy([first, second])
    assert result.readable_by == frozenset({"expert"})
    assert result.egress == "DENY"
    assert derive_policy([]).egress == "DENY"
