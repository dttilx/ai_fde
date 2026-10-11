import subprocess
import sys
from uuid import uuid4

from langgraph.types import Command

from app.diagnosis.checkpoints import checkpoint_store, initialize_checkpoints
from app.diagnosis.graph import build_graph


def test_postgres_checkpoint_survives_fresh_process_and_rechecks_safety():
    initialize_checkpoints()
    thread = str(uuid4())
    config = {"configurable": {"thread_id": thread}, "recursion_limit": 32}
    calls = []

    def retrieve(state):
        calls.append("retrieve")
        return {"status": "RETRIEVING"}

    with checkpoint_store() as store:
        graph = build_graph(store, {"retrieve": retrieve})
        graph.invoke(
            {
                "diagnosis_run_id": thread,
                "facts": {"alarm_code": "A310"},
                "needed_information": True,
                "question": "上游压力是多少？",
            },
            config,
        )
        assert graph.get_state(config).next == ("ask_information",)
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.diagnosis.checkpoints import checkpoint_store; "
            "from app.diagnosis.graph import build_graph; import sys; "
            "c={'configurable':{'thread_id':sys.argv[1]}}; "
            "s=checkpoint_store(); p=s.__enter__(); "
            "assert build_graph(p).get_state(c).next == ('ask_information',); "
            "s.__exit__(None,None,None); print('restored')",
            thread,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert child.stdout.strip() == "restored"
    with checkpoint_store() as store:
        graph = build_graph(store, {"retrieve": retrieve})
        graph.invoke(Command(resume={"alarm_code": "A205"}), config)
        assert graph.get_state(config).next == ("expert_review",)
        graph.invoke(Command(resume={"acknowledged": True}), config)
        assert graph.get_state(config).values["status"] == "ESCALATED"
    assert calls == ["retrieve"]  # danger after resume never reaches ordinary retrieval.
