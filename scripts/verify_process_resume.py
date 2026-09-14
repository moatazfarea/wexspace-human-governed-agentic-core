"""Run a real process-kill/restart proof on synthetic data; no cloud credentials."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from wexspace_human_governed_core.runtime import GovernedRuntime
from wexspace_human_governed_core.state import NODE_ORDER

WORK_ID = "AFH-PUBLIC-REPLAY-001"

def main() -> None:
    if os.name != "posix":
        raise RuntimeError("This SIGKILL proof requires a POSIX host")
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "replay-evidence").resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="afh-replay-") as tmp:
        state = Path(tmp) / "state"
        ready = Path(tmp) / "ready.json"
        child_code = r"""
import json, os, sys, time
from pathlib import Path
from wexspace_human_governed_core.runtime import GovernedRuntime
state, ready, work_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
runtime = GovernedRuntime(state)
runtime.create_work(work_id, "Reconcile synthetic receiving evidence", {
    "request_id": "SYNTHETIC-PO-001", "expected_quantity": 120, "observed_quantity": 118
})
status = runtime.run_deterministic(work_id, stop_after=1)
assert status["work"]["cursor"] == 1
assert runtime.repo.effect_count(work_id, "tool:inspect_request") == 1
ready.write_text(json.dumps({"pid": os.getpid(), "cursor": 1}))
while True:
    time.sleep(1)
"""
        process_a = subprocess.Popen(
            [sys.executable, "-c", child_code, str(state), str(ready), WORK_ID],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.monotonic() + 20
        try:
            while not ready.exists():
                if process_a.poll() is not None:
                    raise RuntimeError("Process A exited before its durable cursor: " + process_a.stderr.read())
                if time.monotonic() > deadline:
                    raise TimeoutError("Process A did not reach cursor 1")
                time.sleep(0.05)
            before = json.loads(ready.read_text())
            assert before["pid"] == process_a.pid
            process_a.kill()
            process_a.wait(timeout=10)
            assert process_a.returncode == -signal.SIGKILL
        finally:
            if process_a.poll() is None:
                process_a.kill()
                process_a.wait(timeout=10)
        child_b = r"""
import json, os, sys
from pathlib import Path
from wexspace_human_governed_core.runtime import GovernedRuntime
runtime = GovernedRuntime(Path(sys.argv[1]))
work_id = sys.argv[2]
cursor = runtime.repo.work(work_id)["cursor"]
assert cursor == 1
status = runtime.run_deterministic(work_id)
print(json.dumps({"pid": os.getpid(), "cursor_before": cursor, "cursor_after": status["work"]["cursor"]}))
"""
        second = subprocess.run(
            [sys.executable, "-c", child_b, str(state), WORK_ID],
            check=True, capture_output=True, text=True, timeout=20,
        )
        after = json.loads(second.stdout)
        assert after["pid"] != before["pid"]
        runtime = GovernedRuntime(state)
        status = runtime.status(WORK_ID)
        assert status["work"]["cursor"] == 3
        assert status["work"]["state"] == "HUMAN_REVIEW"
        assert status["evidence_valid"]
        counts = {name: runtime.repo.effect_count(WORK_ID, "tool:" + name) for name in NODE_ORDER}
        assert all(value == 1 for value in counts.values())
        decision, evidence = runtime.export_review_package(WORK_ID, out)
        package = json.loads(decision.read_text())
        assert package["decision_state"] == "HUMAN_REVIEW_REQUIRED"
        assert package["agent_may_auto_approve"] is False
        assert package["reconciliation"]["delta"] == -2
        before_replay = runtime.ledger.read_all()
        runtime.run_deterministic(WORK_ID)
        assert runtime.ledger.read_all() == before_replay
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (decision, evidence)}
        receipt = {
            "work_id": WORK_ID,
            "source_commit": os.environ.get("GITHUB_SHA", "unbound-local"),
            "execution_mode": "REAL_LOCAL_PROCESSES_DETERMINISTIC_TOOLS",
            "cloud_model_invoked": False,
            "process_a": before, "termination": "SIGKILL", "return_code": process_a.returncode,
            "process_b": after, "exact_resume": "PASS",
            "no_duplicate_side_effect": "PASS", "effect_counts": counts,
            "state_readback": "PASS", "human_gate": "PASS",
            "evidence_integrity": "PASS", "completed_replay_noop": "PASS",
            "artifact_sha256": hashes,
            "limitation": "Kill occurs after durable cursor publication; external distributed effects are not tested.",
        }
        (out / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps(receipt, sort_keys=True))

if __name__ == "__main__":
    main()
