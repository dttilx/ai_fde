import json
import logging


def log_event(event: str, *, trace_id: str, code: str = "OK") -> None:
    """Allowlisted operational fields only; never request bodies, exception text or credentials."""
    logging.getLogger("apx240").info(
        json.dumps({"event": event, "trace_id": trace_id, "code": code})
    )
