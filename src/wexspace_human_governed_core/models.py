from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class NodeState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class WorkState(str, Enum):
    OPEN = "OPEN"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class CompiledRequest:
    objective: str
    required_fields: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    human_boundary: str
    deliverables: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in ("required_fields", "prohibited_actions", "deliverables"):
            d[key] = list(d[key])
        return d


@dataclass(frozen=True)
class ToolResult:
    node: str
    status: str
    payload: dict[str, Any]
