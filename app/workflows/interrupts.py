from __future__ import annotations


def proposal_interrupt_payload(*, proposal_type: str, title: str, rationale: str) -> dict[str, str]:
    return {
        "proposal_type": proposal_type,
        "title": title,
        "rationale": rationale,
        "state": "pending",
    }
