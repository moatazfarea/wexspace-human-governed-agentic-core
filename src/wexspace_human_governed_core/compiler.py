from __future__ import annotations

from .models import CompiledRequest


def compile_request(objective: str) -> CompiledRequest:
    objective = " ".join(objective.split()).strip()
    if not objective:
        raise ValueError("objective must not be empty")
    return CompiledRequest(
        objective=objective,
        required_fields=("request_id", "expected_quantity", "observed_quantity"),
        prohibited_actions=("auto_approve", "publish_without_review"),
        human_boundary="HUMAN_REVIEW",
        deliverables=("decision_package.json", "evidence_manifest.json"),
    )
