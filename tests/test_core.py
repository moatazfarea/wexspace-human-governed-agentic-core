from pathlib import Path

import pytest

from wexspace_human_governed_core.compiler import compile_request
from wexspace_human_governed_core.evidence import EvidenceLedger
from wexspace_human_governed_core.runtime import GovernedRuntime
from wexspace_human_governed_core.state import WorkRepository
from wexspace_human_governed_core.tools import inspect_request, reconcile_evidence


def inputs():
    return {"request_id": "REQ-001", "expected_quantity": 10, "observed_quantity": 9}


def test_compiler_contract():
    c = compile_request(" Reconcile   receiving evidence ")
    assert c.objective == "Reconcile receiving evidence"
    assert "auto_approve" in c.prohibited_actions
    assert c.human_boundary == "HUMAN_REVIEW"


def test_compiler_rejects_empty():
    with pytest.raises(ValueError):
        compile_request("   ")


def test_inspect_detects_missing():
    result = inspect_request({"request_id": "x"})
    assert result.status == "MISSING_INPUT"
    assert "expected_quantity" in result.payload["missing"]


def test_reconciliation_is_deterministic():
    result = reconcile_evidence(inputs())
    assert result.payload["delta"] == -1
    assert result.payload["reconciled"] is False


def test_evidence_integrity(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ledger.append({"type": "x", "value": 1})
    assert ledger.verify()


def test_end_to_human_review(tmp_path: Path):
    rt = GovernedRuntime(tmp_path)
    rt.create_work("W1", "Reconcile evidence", inputs())
    status = rt.run_deterministic("W1")
    assert status["work"]["state"] == "HUMAN_REVIEW"
    assert status["evidence_valid"] is True
    assert status["nodes"]["prepare_review_package"]["output"]["agent_may_auto_approve"] is False


def test_agent_cannot_auto_approve(tmp_path: Path):
    rt = GovernedRuntime(tmp_path)
    rt.create_work("W1", "Reconcile evidence", inputs())
    rt.run_deterministic("W1")
    assert rt.repo.work("W1")["state"] == "HUMAN_REVIEW"
    rt.repo.review("W1", "owner", True)
    assert rt.repo.work("W1")["state"] == "APPROVED"


def test_review_before_gate_forbidden(tmp_path: Path):
    rt = GovernedRuntime(tmp_path)
    rt.create_work("W1", "Reconcile evidence", inputs())
    with pytest.raises(RuntimeError):
        rt.repo.review("W1", "owner", True)


def test_exact_resume_and_no_duplicate_effect(tmp_path: Path):
    rt1 = GovernedRuntime(tmp_path)
    rt1.create_work("W1", "Reconcile evidence", inputs())
    rt1.run_deterministic("W1", stop_after=1)
    assert rt1.repo.work("W1")["cursor"] == 1
    assert rt1.repo.effect_count("W1", "tool:inspect_request") == 1

    rt2 = GovernedRuntime(tmp_path)
    rt2.run_deterministic("W1")
    assert rt2.repo.work("W1")["state"] == "HUMAN_REVIEW"
    assert rt2.repo.effect_count("W1", "tool:inspect_request") == 1
    assert rt2.repo.effect_count("W1", "tool:reconcile_evidence") == 1
    assert rt2.repo.effect_count("W1", "tool:prepare_review_package") == 1


def test_export_native_outputs(tmp_path: Path):
    rt = GovernedRuntime(tmp_path / "state")
    rt.create_work("W1", "Reconcile evidence", inputs())
    rt.run_deterministic("W1")
    decision, evidence = rt.export_review_package("W1", tmp_path / "out")
    assert decision.exists() and decision.stat().st_size > 0
    assert evidence.exists() and evidence.stat().st_size > 0


def test_rcs_prevents_identical_failed_route(tmp_path: Path):
    repo = WorkRepository(tmp_path / "db.sqlite3")
    repo.create("W1", "x", inputs())
    repo.register_failure_attempt("W1", "network-502", "route-a", "state-1")
    with pytest.raises(RuntimeError, match="identical failed route"):
        repo.register_failure_attempt("W1", "network-502", "route-a", "state-1")
    repo.register_failure_attempt("W1", "network-502", "route-b", "state-1")
    repo.register_failure_attempt("W1", "network-502", "route-a", "state-2")
