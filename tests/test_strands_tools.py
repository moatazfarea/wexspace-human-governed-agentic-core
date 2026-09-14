"""Exercise the installed Strands SDK tool dispatcher; no model is invoked."""
import json
from importlib.metadata import version
from time import perf_counter

import pytest
from botocore.client import BaseClient
from strands.models import BedrockModel

from wexspace_human_governed_core.runtime import GovernedRuntime
from wexspace_human_governed_core.state import NODE_ORDER
from wexspace_human_governed_core.strands_runtime import build_strands_agent


@pytest.fixture
def connected_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")

    def forbid_provider_request(*args, **kwargs):
        raise AssertionError("This SDK tool test must not invoke a cloud provider")

    monkeypatch.setattr(BaseClient, "_make_api_call", forbid_provider_request)
    runtime = GovernedRuntime(tmp_path / "state")
    work_id = "SDK-SYNTHETIC-001"
    runtime.create_work(work_id, "Reconcile synthetic receiving evidence.", {
        "request_id": "SYNTHETIC-001",
        "expected_quantity": 120,
        "observed_quantity": 118,
    })
    model = BedrockModel(model_id="us.amazon.nova-pro-v1:0", region_name="us-east-1")
    agent = build_strands_agent(runtime, work_id, model=model)
    return runtime, work_id, agent


def test_real_sdk_repeated_named_tools_do_not_advance_other_nodes(connected_tools):
    runtime, work_id, agent = connected_tools
    started = perf_counter()
    assert set(agent.tool_names) == {f"{node}_tool" for node in NODE_ORDER}
    for cursor, node in enumerate(NODE_ORDER, 1):
        call = getattr(agent.tool, f"{node}_tool")
        result = call()
        assert result["status"] == "success", result
        assert runtime.repo.work(work_id)["cursor"] == cursor
        original_output = runtime.repo.node(work_id, node)["output"]
        ledger_before = runtime.ledger.read_all()
        replay = call()
        assert replay["status"] == "success", replay
        assert runtime.repo.work(work_id)["cursor"] == cursor, (
            f"Replaying {node} must not execute the next node"
        )
        assert runtime.repo.node(work_id, node)["output"] == original_output
        assert runtime.ledger.read_all() == ledger_before
        assert "reused" in json.dumps(replay)
    final = runtime.status(work_id)
    assert final["work"]["state"] == "HUMAN_REVIEW"
    decision = final["nodes"]["prepare_review_package"]["output"]
    assert decision["agent_may_auto_approve"] is False
    assert decision["reconciliation"]["delta"] == -2
    assert all(runtime.repo.effect_count(work_id, f"tool:{n}") == 1 for n in NODE_ORDER)
    assert runtime.ledger.verify()
    print(json.dumps({
        "qualification": "REAL_STRANDS_SDK_DIRECT_TOOL_EXECUTION",
        "strands_version": version("strands-agents"),
        "model_inference": False,
        "tool_calls": 6,
        "named_tool_replay": "PASS",
        "human_gate": "PASS",
        "elapsed_ms": round((perf_counter() - started) * 1000, 3),
    }, sort_keys=True))


@pytest.mark.parametrize("name", ["reconcile_evidence_tool", "prepare_review_package_tool"])
def test_real_sdk_blocks_out_of_order_tool(connected_tools, name):
    runtime, work_id, agent = connected_tools
    before = runtime.ledger.read_all()
    result = getattr(agent.tool, name)()
    assert result["status"] == "error", result
    assert runtime.repo.work(work_id)["cursor"] == 0
    assert runtime.ledger.read_all() == before
    assert all(runtime.repo.effect_count(work_id, f"tool:{n}") == 0 for n in NODE_ORDER)


def test_real_sdk_missing_input_does_not_claim_pass(connected_tools):
    runtime, _, agent = connected_tools
    runtime.create_work("MISSING-001", "Inspect incomplete synthetic evidence.", {})
    missing_agent = build_strands_agent(runtime, "MISSING-001", model=agent.model)
    result = missing_agent.tool.inspect_request_tool()
    assert "MISSING_INPUT" in json.dumps(result)
    assert runtime.repo.work("MISSING-001")["cursor"] == 0
    assert runtime.repo.node("MISSING-001", "inspect_request")["state"] == "PENDING"
