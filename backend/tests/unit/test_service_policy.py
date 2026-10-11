from datetime import UTC, datetime, timedelta

import pytest

from app.incidents.service_policy import service_boundary, warranty_status

NOW = datetime(2026, 10, 4, tzinfo=UTC)


@pytest.mark.parametrize(
    "start,end,basis,expected",
    [
        (NOW - timedelta(days=1), NOW, "contract:1", "ACTIVE"),
        (NOW - timedelta(days=2), NOW - timedelta(seconds=1), "contract:1", "EXPIRED"),
        (NOW + timedelta(days=1), NOW + timedelta(days=2), "contract:1", "UNKNOWN"),
        (NOW, NOW - timedelta(days=1), "contract:1", "UNKNOWN"),
        (None, NOW, "contract:1", "UNKNOWN"),
        (NOW, None, "contract:1", "UNKNOWN"),
        (NOW, NOW, "", "UNKNOWN"),
        (NOW, NOW, "   ", "UNKNOWN"),
        (NOW.replace(tzinfo=None), NOW, "contract:1", "UNKNOWN"),
    ],
)
def test_warranty_dates_require_sourced_aware_valid_interval(start, end, basis, expected):
    assert warranty_status(start, end, basis, NOW) == expected


def test_unknown_warranty_is_not_an_invented_service_restriction():
    result = service_boundary("UNKNOWN", "CHECK_WIRING", [], NOW)
    assert result["status"] == "NO_CONFIRMED_RESTRICTION"
    assert result["restrictions"] == []
    assert result["permits_repair"] is False
    assert result["warranty_status"] == "UNKNOWN"


def test_only_confirmed_in_force_matching_sourced_terms_apply():
    valid = {
        "restriction_id": "term-1",
        "action_kind": "CHECK_WIRING",
        "required_service_party": "authorized-vendor",
        "basis_ref": "contract:1#section2",
        "version": 1,
        "confirmed": True,
        "effective_from": NOW - timedelta(days=1),
        "effective_until": NOW,
    }
    invalid = [
        {**valid, "basis_ref": ""},
        {**valid, "confirmed": False},
        {**valid, "effective_until": NOW - timedelta(seconds=1)},
        {**valid, "action_kind": "PRESSURE_DISASSEMBLY"},
    ]
    result = service_boundary("ACTIVE", "CHECK_WIRING", [valid, *invalid], NOW)
    assert result["status"] == "SERVICE_PARTY_REQUIRED"
    assert len(result["restrictions"]) == 1
    assert result["restrictions"][0]["basis_ref"] == "contract:1#section2"
    assert result["permits_repair"] is False


def test_expired_warranty_does_not_cancel_separately_effective_service_terms():
    term = {
        "restriction_id": "term-1",
        "action_kind": "CHECK_WIRING",
        "required_service_party": "vendor",
        "basis_ref": "service:1",
        "version": 1,
        "confirmed": True,
        "effective_from": NOW - timedelta(days=1),
        "effective_until": NOW + timedelta(days=1),
    }
    assert (
        service_boundary("EXPIRED", "CHECK_WIRING", [term], NOW)["status"]
        == "SERVICE_PARTY_REQUIRED"
    )
