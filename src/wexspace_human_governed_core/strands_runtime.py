from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .runtime import GovernedRuntime


class ProviderAuthRequired(RuntimeError):
    pass


def build_bedrock_model():
    try:
        from strands.models import BedrockModel
    except Exception as exc:  # pragma: no cover - exercised in live environment
        raise RuntimeError("Strands Bedrock provider is not installed") from exc

    model_id = os.environ.get("WEXSPACE_BEDROCK_MODEL_ID")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not model_id or not region:
        raise ProviderAuthRequired(
            "Set WEXSPACE_BEDROCK_MODEL_ID and AWS_REGION after live Bedrock model discovery; credentials use the standard AWS provider chain."
        )
    return BedrockModel(model_id=model_id, region_name=region, temperature=0.1)


def build_strands_agent(runtime: GovernedRuntime, work_id: str, model=None):
    try:
        from strands import Agent, tool
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("strands-agents is not installed") from exc

    if model is None:
        model = build_bedrock_model()

    @tool
    def inspect_request_tool() -> dict[str, Any]:
        """Inspect the professional request and persist the deterministic inspection result."""
        before = runtime.repo.work(work_id)["cursor"]
        runtime.run_deterministic(work_id, stop_after=1)
        after = runtime.repo.work(work_id)["cursor"]
        return {"cursor_before": before, "cursor_after": after, "node": "inspect_request"}

    @tool
    def reconcile_evidence_tool() -> dict[str, Any]:
        """Run deterministic evidence reconciliation and persist the result."""
        work = runtime.repo.work(work_id)
        if work["cursor"] < 1:
            raise RuntimeError("inspect_request must complete first")
        before = work["cursor"]
        runtime.run_deterministic(work_id, stop_after=1)
        after = runtime.repo.work(work_id)["cursor"]
        return {"cursor_before": before, "cursor_after": after, "node": "reconcile_evidence"}

    @tool
    def prepare_review_package_tool() -> dict[str, Any]:
        """Prepare the evidence-backed package and stop at the human review boundary."""
        work = runtime.repo.work(work_id)
        if work["cursor"] < 2:
            raise RuntimeError("reconciliation must complete first")
        before = work["cursor"]
        runtime.run_deterministic(work_id, stop_after=1)
        after = runtime.repo.work(work_id)["cursor"]
        return {
            "cursor_before": before,
            "cursor_after": after,
            "node": "prepare_review_package",
            "human_review_required": True,
            "auto_approval_allowed": False,
        }

    system_prompt = """
You are WEXSPACE AI — Human-Governed Agentic Core.
Perform the professional workflow end to end using the registered tools in order.
Never perform deterministic arithmetic yourself when a deterministic tool exists.
Persisted tool/state results are authoritative.
Do not repeat a completed tool effect after restart.
Never approve, reject, publish, send, or finalize the consequential decision.
Stop once HUMAN_REVIEW is reached and report the evidence-backed review state.
""".strip()

    return Agent(
        model=model,
        tools=[inspect_request_tool, reconcile_evidence_tool, prepare_review_package_tool],
        system_prompt=system_prompt,
    )


def invoke_live_bedrock(state_dir: Path, work_id: str, prompt: str):
    runtime = GovernedRuntime(state_dir)
    agent = build_strands_agent(runtime, work_id)
    runtime.ledger.append({"type": "live_agent_invocation_started", "work_id": work_id, "provider": "bedrock"})
    response = agent(prompt)
    runtime.ledger.append({"type": "live_agent_invocation_completed", "work_id": work_id, "provider": "bedrock"})
    return response
