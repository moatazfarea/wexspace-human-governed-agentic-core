"""Qualify real LangGraph persistence around WEXSPACE deterministic tools."""
import json
import os
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from wexspace_human_governed_core.runtime import GovernedRuntime
from wexspace_human_governed_core.state import NODE_ORDER


WORK_ID = "FLEET-LANGGRAPH-SYNTHETIC-001"


class State(TypedDict):
    work_id: str


def worker(stage, root):
    runtime = GovernedRuntime(root / "core")
    calls = root / "calls.jsonl"

    def record(name):
        with calls.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"node": name, "pid": os.getpid()}) + "\n")

    def inspect(state):
        record("inspect")
        assert runtime.repo.work(WORK_ID)["cursor"] == 0
        runtime.run_deterministic(WORK_ID, stop_after=1)
        return {}

    def technical_checkpoint(state):
        interrupt({"kind": "TECHNICAL_PAUSE", "work_id": WORK_ID, "cursor": 1})
        return {}

    def reconcile(state):
        record("reconcile")
        assert runtime.repo.work(WORK_ID)["cursor"] == 1
        runtime.run_deterministic(WORK_ID, stop_after=1)
        return {}

    def prepare(state):
        record("prepare")
        assert runtime.repo.work(WORK_ID)["cursor"] == 2
        runtime.run_deterministic(WORK_ID, stop_after=1)
        return {}

    builder = StateGraph(State)
    for name, fn in [("inspect", inspect), ("pause", technical_checkpoint),
                     ("reconcile", reconcile), ("prepare", prepare)]:
        builder.add_node(name, fn)
    for left, right in [(START, "inspect"), ("inspect", "pause"),
                        ("pause", "reconcile"), ("reconcile", "prepare"), ("prepare", END)]:
        builder.add_edge(left, right)
    config = {"configurable": {"thread_id": WORK_ID}}
    with SqliteSaver.from_conn_string(str(root / "graph.sqlite3")) as saver:
        graph = builder.compile(checkpointer=saver)
        if stage == "start":
            runtime.create_work(WORK_ID, "Reconcile synthetic evidence.", {
                "request_id": "SYNTHETIC-001", "expected_quantity": 120, "observed_quantity": 118,
            })
            result = graph.invoke({"work_id": WORK_ID}, config)
            assert result["__interrupt__"]
            assert runtime.repo.work(WORK_ID)["cursor"] == 1
        else:
            snapshot = graph.get_state(config)
            assert snapshot.values["work_id"] == WORK_ID
            assert snapshot.next == ("pause",)
            graph.invoke(Command(resume={"continue_safe_tools": True}), config)
            status = runtime.status(WORK_ID)
            assert status["work"]["state"] == "HUMAN_REVIEW"
            assert status["nodes"]["prepare_review_package"]["output"]["agent_may_auto_approve"] is False
            assert status["nodes"]["reconcile_evidence"]["output"]["delta"] == -2
            assert runtime.ledger.verify()
            assert all(runtime.repo.effect_count(WORK_ID, f"tool:{n}") == 1 for n in NODE_ORDER)
    print(json.dumps({"stage": stage, "pid": os.getpid(), "cursor": runtime.repo.work(WORK_ID)["cursor"]}))


if __name__ == "__main__":
    if len(sys.argv) == 3:
        worker(sys.argv[1], Path(sys.argv[2]))
    else:
        started = perf_counter()
        with tempfile.TemporaryDirectory(prefix="wexspace-langgraph-") as directory:
            root = Path(directory)
            receipts = []
            for stage in ["start", "resume"]:
                process = subprocess.run(
                    [sys.executable, __file__, stage, str(root)], check=True, text=True,
                    capture_output=True, timeout=90,
                )
                receipts.append(json.loads(process.stdout.splitlines()[-1]))
            assert receipts[0]["pid"] != receipts[1]["pid"]
            calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
            assert [row["node"] for row in calls] == ["inspect", "reconcile", "prepare"]
            print(json.dumps({
                "capability": "LANGGRAPH_DURABLE_TOOL_WORKFLOW",
                "state": "QUALIFIED",
                "versions": {p: version(p) for p in ["langgraph", "langgraph-checkpoint-sqlite"]},
                "real_tool_callbacks": len(calls),
                "fresh_process_checkpoint_reuse": "PASS",
                "duplicate_effects": 0,
                "human_authority": "HUMAN_REVIEW",
                "model_inference": False,
                "control_plane": "LOCAL_OPEN_SOURCE_RUNTIME",
                "processes": receipts,
                "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                "limitation": "Deterministic graph with technical interrupt; no live model or distributed transaction.",
            }, sort_keys=True))
