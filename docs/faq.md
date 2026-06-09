# FAQ

## Why is this not just an LLM wrapper?

The backend is an Agent pipeline, not a direct prompt proxy. User requests pass
through intent routing, context building, knowledge retrieval, tool planning,
safe Proposal generation, result recording, diagnostics, and evaluation.

## Why keep a local knowledge base if the LLM already knows Unreal Engine?

The local knowledge base gives the Agent project-specific and curated evidence.
It also makes answers more inspectable: the backend can show which files were
retrieved and when retrieval was weak. If vector search is disabled, the backend
still uses lexical/local search over Markdown and code references.

## Is Qdrant required?

No. The default local setup can run without Qdrant:

```env
EMBEDDING_ENABLED=false
RAG_FALLBACK_MODE=lexical_only
```

When Qdrant and embeddings are available, the backend can use vector or hybrid
retrieval. Code-oriented lookup can still use local grep-style evidence.

## Why not let the LLM directly edit `.uasset` files?

Unreal assets are binary/editor-managed files. The project intentionally keeps
writes inside Unreal Editor through UEAgentTool and Editor APIs. The backend only
creates confirmed-write Proposals; the user must confirm before UEAgentTool
executes the operation.

## Why can some editor operation proposals work when the LLM is offline?

Some editor operations have deterministic routing and payload builders. If the
intent is clear enough, the backend can create a Proposal without a live LLM.
This is a fallback path, not hidden execution. The user still has to confirm in
the UE plugin before any editor write happens.

## Does the backend auto-save packages?

No. Editor operations are designed to mark packages dirty and return result
metadata. Saving stays under user control in Unreal Editor.

## What should I do if a Blueprint node is created but not connected?

Check:

```http
GET /api/v1/editor-operations/history?needs_user_attention=true
GET /api/v1/editor-operations/diagnostics
GET /api/v1/editor-operations/proposals/{proposal_id}/follow-ups
```

The follow-up endpoint can return a `connect_blueprint_nodes` candidate, but it
does not create or execute the Proposal automatically.

If this happened inside a multi-step workflow, call
`POST /api/v1/editor-operations/workflows/state` with the original plan. The
workflow state will keep the dependent compile step blocked and expose
`follow_up_proposal_requests[]` for creating a pending repair Proposal. After
the repair Proposal is confirmed, executed, and reported successfully, the same
workflow state endpoint will mark the source step as `completed_after_repair`
and unlock the next step.

## Are private notes or external course repositories included?

No. Public knowledge lives in `knowledge/`. Private notes or third-party source
repositories should be attached locally with `KB_SOURCE_PATHS` and should not be
committed to the public backend repository.

## What tests should contributors run first?

Fast checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q
```

Editor operation smoke checks:

```powershell
.\.venv\Scripts\python.exe scripts\run_blueprint_graph_operation_smoke.py
.\.venv\Scripts\python.exe scripts\run_editor_operation_chat_bridge_smoke.py
```
