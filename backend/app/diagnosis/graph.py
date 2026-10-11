from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.diagnosis.state import DiagnosisState
from app.safety.service import evaluate
from app.shared.versioning import content_hash

GRAPH_VERSION = "apx240-graph-v2.8"


def build_graph(checkpointer, overrides: dict[str, Callable] | None = None):
    """Foundation graph; service nodes are wired by the later diagnostic tasks."""

    def prepare(state: DiagnosisState):
        return {
            "status": "SAFETY_CHECK",
            "evidence_snapshot_hash": content_hash(state.get("facts", {})),
        }

    def safety_gate(state: DiagnosisState):
        decision = evaluate(
            state.get("raw_text", ""),
            state.get("facts", {}),
            tuple(state.get("qualifications", ())),
        )
        return {"status": "SAFETY_CHECK", "safety": decision.model_dump()}

    def retrieve(state: DiagnosisState):
        return {"status": "RETRIEVING", "retrieved": []}

    def decide(state: DiagnosisState):
        return {"status": "NEEDS_INFORMATION" if state.get("needed_information") else "FINALIZING"}

    def ask_information(state: DiagnosisState):
        answer = interrupt(
            {"type": "INFORMATION", "question": state.get("question", "请补充必要信息。")}
        )
        return {"facts": {**state.get("facts", {}), **answer}, "needed_information": False}

    def expert_review(state: DiagnosisState):
        disposition = interrupt({"type": "EXPERT", "safety": state["safety"]})
        # An acknowledgement never clears deterministic risk or grants maintenance permission.
        return {"expert_disposition": disposition, "status": "ESCALATED"}

    def finalize(state: DiagnosisState):
        return {
            "status": "ESCALATED" if state.get("safety", {}).get("safety_blocked") else "COMPLETED"
        }

    nodes = {
        "prepare": prepare,
        "safety_gate": safety_gate,
        "retrieve": retrieve,
        "decide": decide,
        "ask_information": ask_information,
        "expert_review": expert_review,
        "finalize": finalize,
    }
    nodes.update(overrides or {})
    graph = StateGraph(DiagnosisState)
    for name, handler in nodes.items():
        graph.add_node(name, handler)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "safety_gate")
    graph.add_conditional_edges(
        "safety_gate",
        lambda state: "expert_review" if state["safety"]["safety_blocked"] else "retrieve",
    )
    graph.add_edge("retrieve", "decide")
    graph.add_conditional_edges(
        "decide",
        lambda state: (
            "expert_review"
            if state.get("safety", {}).get("safety_blocked") or state["status"] == "WAITING_EXPERT"
            else "safety_gate"
            if state["status"] == "RETRIEVING"
            else "ask_information"
            if state["status"] == "NEEDS_INFORMATION"
            else "finalize"
        ),
    )
    graph.add_edge("ask_information", "safety_gate")
    graph.add_edge("expert_review", "finalize")
    graph.add_conditional_edges(
        "finalize",
        lambda state: "expert_review" if state["status"] == "CONFLICT_BLOCKED" else END,
    )
    return graph.compile(checkpointer=checkpointer)
