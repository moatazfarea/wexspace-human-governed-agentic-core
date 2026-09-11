from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .compiler import compile_request
from .evidence import EvidenceLedger
from .state import NODE_ORDER, WorkRepository
from .tools import inspect_request, prepare_review_package, reconcile_evidence


class GovernedRuntime:
    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.repo = WorkRepository(self.state_dir / "work.sqlite3")
        self.ledger = EvidenceLedger(self.state_dir / "evidence.jsonl")

    def create_work(self, work_id: str, objective: str, inputs: dict[str, Any]) -> None:
        compiled = compile_request(objective)
        self.repo.create(work_id, objective, inputs)
        self.ledger.append({"type": "work_created", "work_id": work_id, "compiled": compiled.to_dict()})

    def run_deterministic(self, work_id: str, stop_after: int | None = None) -> dict[str, Any]:
        work = self.repo.work(work_id)
        steps_done = 0
        while work["cursor"] < len(NODE_ORDER):
            if stop_after is not None and steps_done >= stop_after:
                break
            node = NODE_ORDER[work["cursor"]]
            inputs = work["inputs"]
            if node == "inspect_request":
                result = inspect_request(inputs)
                if result.status != "PASS":
                    self.ledger.append({"type": "missing_input", "work_id": work_id, "payload": result.payload})
                    return {"state": "MISSING_INPUT", "payload": result.payload}
            elif node == "reconcile_evidence":
                result = reconcile_evidence(inputs)
            elif node == "prepare_review_package":
                inspect_payload = self.repo.node(work_id, "inspect_request")["output"]
                reconcile_payload = self.repo.node(work_id, "reconcile_evidence")["output"]
                result = prepare_review_package(inspect_payload, reconcile_payload)
            else:
                raise AssertionError(node)

            effect_key = f"tool:{node}"
            first_effect = self.repo.record_effect_once(work_id, effect_key, result.payload)
            self.repo.set_node_pass(work_id, node, result.payload)
            self.ledger.append({
                "type": "node_pass",
                "work_id": work_id,
                "node": node,
                "status": result.status,
                "payload": result.payload,
                "side_effect_created": first_effect,
            })
            steps_done += 1
            work = self.repo.work(work_id)
        return self.status(work_id)

    def status(self, work_id: str) -> dict[str, Any]:
        work = self.repo.work(work_id)
        nodes = {name: self.repo.node(work_id, name) for name in NODE_ORDER}
        return {"work": work, "nodes": nodes, "evidence_valid": self.ledger.verify()}

    def export_review_package(self, work_id: str, out_dir: Path) -> tuple[Path, Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        status = self.status(work_id)
        if status["work"]["state"] != "HUMAN_REVIEW":
            raise RuntimeError("work has not reached HUMAN_REVIEW")
        decision_path = out_dir / "decision_package.json"
        evidence_path = out_dir / "evidence_manifest.json"
        decision = status["nodes"]["prepare_review_package"]["output"]
        decision_path.write_text(json.dumps(decision, indent=2, sort_keys=True), encoding="utf-8")
        evidence_path.write_text(json.dumps(self.ledger.read_all(), indent=2, sort_keys=True), encoding="utf-8")
        return decision_path, evidence_path
