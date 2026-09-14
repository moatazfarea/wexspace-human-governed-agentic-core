from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from .runtime import GovernedRuntime


class AgentCoreDeploymentManifest:
    def __init__(
        self,
        agent_name: str = "WexspaceGovernedAgent",
        foundation_model: str = "amazon.nova-pro-v1:0",
        execution_role_arn: Optional[str] = None,
    ) -> None:
        self.agent_name = agent_name
        self.foundation_model = foundation_model
        self.execution_role_arn = execution_role_arn or os.getenv(
            "WEXSPACE_AGENTCORE_EXECUTION_ROLE_ARN",
            "CONFIGURE_VIA_WEXSPACE_AGENTCORE_EXECUTION_ROLE_ARN",
        )
        self.instruction = (
            "You are WEXSPACE AI operating under strict human governance. "
            "Execute the professional receiving reconciliation workflow using the action group tools. "
            "Never invent arithmetic. Persist all state transitions. "
            "Stop at the human review boundary for consequential decisions."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "foundation_model": self.foundation_model,
            "role_arn": self.execution_role_arn,
            "idle_session_ttl_seconds": 1800,
            "instruction": self.instruction,
            "action_groups": [
                {
                    "action_group_name": "ReconciliationTools",
                    "description": "Deterministic tools for inspecting requests, calculating invoice variances, and preparing review packages",
                    "action_group_state": "ENABLED",
                    "api_schema": {
                        "openapi": "3.0.0",
                        "info": {"title": "WEXSPACE State Actions", "version": "1.0.0"},
                        "paths": {
                            "/inspect_request": {
                                "post": {
                                    "description": "Inspect the professional request",
                                    "responses": {"200": {"description": "Inspection verified"}}
                                }
                            },
                            "/reconcile_evidence": {
                                "post": {
                                    "description": "Calculate discrepancies deterministically",
                                    "responses": {"200": {"description": "Variance calculated"}}
                                }
                            },
                            "/prepare_review_package": {
                                "post": {
                                    "description": "Prepare human review package and halt",
                                    "responses": {"200": {"description": "Review gate reached"}}
                                }
                            }
                        }
                    }
                }
            ],
            "metadata": {
                "framework": "strands-agents 1.55.1 + Bedrock AgentCore bridge",
                "timestamp": time.time(),
                "governance": "WEXSPACE_KNOWLEDGE_ROOT_README_R10"
            }
        }


class AgentCoreRuntime:
    def __init__(self, state_dir: Path, manifest: Optional[AgentCoreDeploymentManifest] = None) -> None:
        self.state_dir = state_dir
        self.runtime = GovernedRuntime(state_dir)
        self.manifest = manifest or AgentCoreDeploymentManifest()

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "HEALTHY",
            "agent_name": self.manifest.agent_name,
            "model": self.manifest.foundation_model,
            "role": self.manifest.execution_role_arn,
            "governance_mode": "FAIL_CLOSED_HUMAN_GATE",
            "timestamp": time.time()
        }

    def execute_governed_turn(self, work_id: str, input_text: str) -> dict[str, Any]:
        work = self.runtime.repo.work(work_id)
        current_cursor = work["cursor"]

        self.runtime.ledger.append({
            "type": "agentcore_invocation_started",
            "work_id": work_id,
            "cursor_before": current_cursor,
            "input": input_text,
            "agent": self.manifest.agent_name
        })

        executed_actions = []

        if current_cursor == 0:
            self.runtime.run_deterministic(work_id, stop_after=1)
            executed_actions.append("inspect_request")
            current_cursor = 1

        if current_cursor == 1:
            self.runtime.run_deterministic(work_id, stop_after=1)
            executed_actions.append("reconcile_evidence")
            current_cursor = 2

        if current_cursor == 2:
            self.runtime.run_deterministic(work_id, stop_after=1)
            executed_actions.append("prepare_review_package")
            current_cursor = 3

        work_after = self.runtime.repo.work(work_id)
        halted_at_gate = work_after["state"] == "HUMAN_REVIEW"

        self.runtime.ledger.append({
            "type": "agentcore_invocation_completed",
            "work_id": work_id,
            "cursor_after": work_after["cursor"],
            "phase": work_after["state"],
            "executed_actions": executed_actions,
            "halted_at_human_gate": halted_at_gate
        })

        return {
            "status": "HALTED_AT_HUMAN_REVIEW" if halted_at_gate else "SUCCESS",
            "work_id": work_id,
            "cursor": work_after["cursor"],
            "phase": work_after["state"],
            "executed_actions": executed_actions,
            "human_decision_required": halted_at_gate,
            "revision": work_after["revision"],
            "evidence_ledger_entries": len(self.runtime.ledger.read_all())
        }
