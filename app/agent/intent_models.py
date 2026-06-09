from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


INTENT_DRAFT_VERSION = "intent_draft_v1"
VERIFIED_INTENT_VERSION = "verified_intent_v1"


@dataclass(slots=True)
class IntentDraft:
    user_goal: str
    intent_type: str
    target_kind: str
    target_reference: str
    needs_project_context: bool
    needs_live_editor_context: bool
    needs_knowledge: bool
    requested_write: bool
    candidate_tools: list[str] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    source: str = "deterministic_router_projection"
    version: str = INTENT_DRAFT_VERSION

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VerifiedIntent:
    intent_type: str
    target_kind: str
    target_resolution_status: str
    selected_tool_id: str | None
    route_type: str
    confidence: float
    corrections: list[dict[str, Any]] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)
    permission_decision: dict[str, Any] = field(default_factory=dict)
    version: str = VERIFIED_INTENT_VERSION

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "INTENT_DRAFT_VERSION",
    "VERIFIED_INTENT_VERSION",
    "IntentDraft",
    "VerifiedIntent",
]
