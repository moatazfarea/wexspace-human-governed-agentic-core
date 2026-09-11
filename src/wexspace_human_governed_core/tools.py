from __future__ import annotations

from typing import Any

from .models import ToolResult


def inspect_request(inputs: dict[str, Any]) -> ToolResult:
    required = ("request_id", "expected_quantity", "observed_quantity")
    missing = [k for k in required if inputs.get(k) is None]
    return ToolResult(
        node="inspect_request",
        status="MISSING_INPUT" if missing else "PASS",
        payload={"missing": missing, "received_fields": sorted(inputs)},
    )


def reconcile_evidence(inputs: dict[str, Any]) -> ToolResult:
    expected = int(inputs["expected_quantity"])
    observed = int(inputs["observed_quantity"])
    delta = observed - expected
    return ToolResult(
        node="reconcile_evidence",
        status="PASS",
        payload={
            "expected_quantity": expected,
            "observed_quantity": observed,
            "delta": delta,
            "reconciled": delta == 0,
        },
    )


def prepare_review_package(inspect_payload: dict[str, Any], reconciliation_payload: dict[str, Any]) -> ToolResult:
    package = {
        "inspection": inspect_payload,
        "reconciliation": reconciliation_payload,
        "decision_state": "HUMAN_REVIEW_REQUIRED",
        "agent_may_auto_approve": False,
    }
    return ToolResult(node="prepare_review_package", status="HUMAN_REVIEW_REQUIRED", payload=package)
