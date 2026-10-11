from app.access.dependencies import require_action
from app.access.qualifications import qualifications
from app.incidents.assets import asset_summary
from app.incidents.models import Incident
from app.incidents.service import current_snapshot
from app.safety.schemas import rule_citations
from app.safety.service import evaluate
from app.shared.db import require_record
from app.shared.errors import DomainError

ACTIONS = {
    "OPEN_GUARD": "打开防护罩",
    "CLEAR_JAM": "清除夹料",
    "CHECK_WIRING": "检查线路",
    "CHECK_HEATER": "检查加热回路及接触加热组件",
    "CHECK_SERVO": "伺服维修",
    "PRESSURE_WORK": "气路拆装",
}


def check_preconditions(db, actor, incident_id, action_kind, asset_id=None):
    require_action(db, actor, "INCIDENT", incident_id, "FIELD_ENGINEER", "EXPERT")
    if action_kind not in ACTIONS:
        raise DomainError("CHECK_ACTION_UNSUPPORTED", 422)
    incident = require_record(db, Incident, incident_id)
    snapshot = current_snapshot(db, incident_id)
    from app.diagnosis.retrieval_context import snapshot_asset_id

    bound_asset = snapshot_asset_id(db, incident, snapshot)
    if asset_id is not None and bound_asset != asset_id:
        raise DomainError("CHECK_ASSET_MISMATCH", 409)
    asset_id = bound_asset
    decision = evaluate(
        incident.raw_description,
        snapshot.facts,
        qualifications(db, actor),
        requested_actions=(ACTIONS[action_kind],),
        contradictions=tuple(snapshot.contradictions),
    )
    rule_ids = set(decision.rule_ids) | {"SAFE-02", "SAFE-03", "SAFE-04"}
    instructions = ["停机、隔离能源、锁定挂牌并确认残余能量释放；由相应授权人员处理。"]
    if action_kind == "PRESSURE_WORK":
        rule_ids.add("A310")
        instructions.append("隔离气源并泄压，禁止带压拆装。")
    if action_kind == "CHECK_HEATER":
        instructions.append("禁止徒手接触加热部件，核实温度与安全处置条件。")
    restrictions = []
    if asset_id:
        summary = asset_summary(db, actor, asset_id)
        restrictions = [
            term
            for boundary in summary["service_boundaries"]
            if boundary["action_kind"] == action_kind
            for term in boundary["restrictions"]
        ]
    return {
        "safety_blocked": decision.safety_blocked or bool(restrictions),
        "qualification_reasons": list(decision.reasons),
        "instructions": instructions,
        "citations": rule_citations(sorted(rule_ids)),
        "service_restrictions": restrictions,
        "allows_device_operation": False,
    }
