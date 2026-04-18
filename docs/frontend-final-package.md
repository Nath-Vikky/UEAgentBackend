# Frontend Final Package

## Preferred Entry

Frontend implementation should now use this file as the single backend handoff entry:

- `docs/frontend-unified-handoff.md`

It already consolidates:

- startup endpoints
- unified chat/task/proposal APIs
- `user_view` / `debug_view` consumption rules
- Proposal confirmation flow
- SSE replay usage
- non-breaking field additions from the latest backend changes
- the minimum file list to hand to the UE frontend engineer

## Read Only If Needed

Use the following files as supplements only when the frontend needs extra detail:

- `docs/task-debugging-guide.md`
- `docs/backend-user-guide.md`
- `../forward.md`
- `app/schemas/requests.py`
- `app/schemas/responses.py`
- `app/schemas/common.py`

## Current Frontend Impact

The latest backend changes do not introduce a breaking contract change.

They add:

- live LLM-backed `direct_answer` when configured
- optional LLM synthesis metadata for `project_qa`
- smarter `agent_chat` routing that no longer forces KB retrieval just because project context is present
- route diagnostics in `debug_view.route` such as `decision_source`, `project_signal_strength`, and optional `llm_route_decision`
- `data.approval_result` after Proposal decisions
- `approved_config` artifacts after confirmed config proposals
- `proposal_followup_completed` in run event replay

Existing UE frontend code that already renders `user_view` and `debug_view` can keep its rendering logic unchanged.
