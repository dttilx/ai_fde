from datetime import datetime


def warranty_status(
    start: datetime | None, end: datetime | None, basis: str | None, clock: datetime
) -> str:
    if (
        not start
        or not end
        or not basis
        or not basis.strip()
        or any(value.utcoffset() is None for value in (start, end, clock))
        or start > end
        or clock < start
    ):
        return "UNKNOWN"
    return "ACTIVE" if clock <= end else "EXPIRED"


def service_boundary(status: str, action: str, terms: list[dict], clock: datetime) -> dict:
    """Sourced service terms constrain the service party, never prove cause or grant repair."""
    applicable = []
    for term in terms:
        start, end = term.get("effective_from"), term.get("effective_until")
        if (
            term.get("confirmed") is not True
            or term.get("action_kind") != action
            or not str(term.get("basis_ref") or "").strip()
            or not str(term.get("required_service_party") or "").strip()
            or not isinstance(start, datetime)
            or not isinstance(end, datetime)
            or any(value.utcoffset() is None for value in (start, end, clock))
            or not start <= clock <= end
        ):
            continue
        applicable.append(
            {
                key: term[key]
                for key in (
                    "restriction_id",
                    "action_kind",
                    "required_service_party",
                    "basis_ref",
                    "version",
                )
            }
        )
    return {
        "status": "SERVICE_PARTY_REQUIRED" if applicable else "NO_CONFIRMED_RESTRICTION",
        "warranty_status": status,
        "restrictions": applicable,
        "permits_repair": False,
    }
