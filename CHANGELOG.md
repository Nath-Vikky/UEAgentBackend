# Changelog

This project follows a lightweight changelog style inspired by Keep a
Changelog. Dates use `YYYY-MM-DD`.

## Unreleased

### Added

- Router SignalDetector registry in compatibility-observer mode, exposing
  `signal_detector_trace` and `top_signal_detector` without changing existing
  routing decisions.
- Task handler adapter layer with a route execution dispatcher, establishing
  the first low-risk step toward splitting `TaskService` into strategy handlers.
- Concrete `DirectAnswerHandler`, moving live direct-chat execution out of
  `TaskService` while keeping the existing `agent_chat` response contract.
- Concrete `ConfigValidateHandler`, moving deterministic config validation out
  of `TaskService` while preserving report artifacts and debug output.
- Concrete executor-backed handlers for Code Review, Logs Analyze, and Code
  Generate, moving thin skill orchestration wrappers out of `TaskService`.
- Concrete workflow-backed handlers for Config Generate and Performance
  Analyze, plus shared task-handler citation preview helpers.
- Concrete `AssetsInspectHandler` and `PlaceholderTaskHandler`, moving asset
  inspection orchestration and fallback diagnostics out of `TaskService`.
- Concrete `EditorOperationProposalHandler`, moving editor-operation proposal
  response shaping out of `TaskService`; removed unused legacy placeholder
  Project QA and Direct Answer execution methods.
- Concrete `ProjectQAHandler`, moving the full Project QA live orchestration
  path out of `TaskService` while preserving RAG, local grep, Web Memory, Web
  Search, Project Inventory, project-file read, and LLM synthesis fields.
- Tool execution context contracts: `ToolContext`, `ToolResult`, and
  `CompositeToolResult` define a stable input/output envelope for future
  executor and MCP transport migration without changing current tool behavior.
- Optional SQLite FTS5 Web Memory recall path with automatic Python-token
  fallback for environments where FTS5 is unavailable or unsuitable.
- Memory Provider adapter layer with `SessionLongTermMemoryProvider` and
  `WebMemoryProvider`, giving context memory a stable provider contract without
  changing current prompt context output.
- Knowledge curation suggestion pipeline for Project QA. It proposes
  human-reviewed KB follow-up candidates when external evidence fills a local
  KB gap, but never writes files or mutates the KB automatically.
- Project file read helper extracted into `app/tools/project_file.py`, keeping
  path containment, suffix allow-listing, and fallback text outside
  `TaskService`.
- Editor operation intent detection, proposal construction, and asset-inspect
  rename proposal generation moved into `EditorOperationService`.
- Project QA deterministic tool planning, ReAct Lite planning, trace building,
  tool-call input lookup, and result-contract validation moved into
  `app/agent/tool_planner.py`.
- Task stream/persisted event envelope helpers extracted into
  `app/services/task_events.py`, keeping SSE and stored task-event sequence
  construction out of `TaskService`.
- Router SignalDetector can now run in optional `scoring_shadow` mode via
  `ROUTER_SIGNAL_MODE=scoring_shadow`, producing a scored route recommendation
  without overriding the existing heuristic route.
- Offline Router Signal eval dataset and runner for measuring heuristic route
  accuracy, scoring-shadow stability, recommendation accuracy, and override
  safety.
- Web Memory recall ranking diagnostics, including per-item ranking breakdown
  and summary ranking policy for lexical, quality, feedback, and FTS5 blend
  scoring.
- ToolContext executor runtime for migrated read-only tools, with
  `read_project_file` and `validate_design_config` now using
  `ToolContext -> executor -> ToolResult` in production paths.
- Knowledge curation artifact exporter:
  `scripts/export_knowledge_curation.py` can turn Project QA curation payloads
  or high-value Web Memory entries into suggestion-only Markdown/JSON review
  files under `storage/curation`.

### Changed

- Agent Chat and Project QA route diagnostics now include signal-detector
  observations for future scoring-router migration and regression analysis.
- Tool Registry capability/debug cards now expose optional `executor` metadata,
  and startup contract validation rejects blank executor strings.
- Web Memory recall now reports `summary.search_mode` and `summary.fts5`
  diagnostics while preserving the existing API shape.
- Context Bundle long-term memory recall now goes through
  `SessionLongTermMemoryProvider`; the returned `long_term_memory` payload is
  intentionally unchanged.
- Project QA responses now include `knowledge_curation` diagnostics in
  `data` and `retrieval_trace`; this is suggestion-only metadata for backend
  maintenance/debugging.
- Project QA now calls the standalone read-only project-file tool helper instead
  of `TaskService` private file-read methods; response fields remain unchanged.
- Route dispatch and task handlers now use `EditorOperationService` directly
  for editor-operation proposals, reducing `TaskService` host callbacks while
  preserving the Proposal confirmation contract.
- `TaskService._execute_route()` now delegates task selection to
  `RouteExecutionDispatcher` while preserving existing response contracts and
  concrete executor behavior.
- Direct free-chat execution is now owned by the task handler layer; RAG,
  Project Inventory, and tool-calling paths are still unchanged.
- Config validation execution is now owned by the task handler layer; it still
  uses the same deterministic `validate_design_config` tool and response shape.
- Code Review, Logs Analyze, and Code Generate still use their existing skill
  executors and multi-agent chain; only the task-handler ownership changed.
- Config Generate and Performance Analyze still use the existing workflow graph
  functions; only task-handler ownership changed.
- Assets Inspect still uses the existing skill executor and confirmed-write
  rename proposal safety path; only task-handler ownership changed.
- Editor operations still use the existing confirmed-write Proposal safety
  boundary; only response ownership changed.
- Project QA still uses the existing retrieval pipeline, inventory service, and
  guarded file-read helper; tool-planning ownership now lives in
  `app/agent/tool_planner.py`, so `TaskService` no longer keeps those private
  helper methods.
- SSE stream events and persisted task events keep the same response shape, but
  their envelope construction is now owned by `app/services/task_events.py`.
- Router diagnostics now include `signal_router_recommendation` and
  `signal_router_override_applied=false`; default routing remains
  `compatibility_observer`.
- Regression suite now includes `scripts/run_router_signal_eval.py`.
- Web Memory response shape is backward compatible; `items[].ranking` and
  `summary.ranking_policy` are additive diagnostics.
- `read_project_file` and `validate_design_config` ToolSpecs now expose concrete
  executor metadata while preserving existing HTTP response contracts.
- Web Memory recall entries now include lightweight `recall_count` diagnostics
  so curation scoring can prioritize repeatedly reused evidence.

## 0.1.4 - 2026-05-16

### Added

- RAG facade, reusable workflow nodes, and an in-process ingestion job queue.
- Integration smoke test guide for the main HTTP workflows.
- Controlled Project QA tool planner module and tool-call sequence debug output.
- Project Inventory field views for focused asset/code metadata answers.
- Bounded log-analysis ReAct debug trace.
- Lightweight CI for Ruff plus unit/contract tests.
- Public architecture and contribution docs.
- Project QA grounding unit tests for inventory-first project facts and generic
  UE knowledge separation.
- Code Review LLM fallback unit tests for malformed JSON-like model responses
  and stable highlight-card analysis output.
- Project QA local grep fallback unit tests for no-vector/no-index retrieval
  traces and explicit local-search skip reasons.
- Optional function-calling adapter that exports read-only Tool Registry entries
  as provider-style function schemas and normalizes tool calls back into the
  existing planner contract.
- Framework-neutral graph adapter blueprint for the existing
  `review_fix_validate` chain, keeping future LangGraph integration optional.
- MCP transport boundary regression for HTTP-as-frontend-protocol and
  proposal-required write policy.
- Assembly Sprint N8 updates: honest Logs Analyze workflow trace, RAG facade
  production wiring for Project QA, Code Review workflow node reuse, and wider
  Code Review rule regression coverage.
- Code Review compact LLM retry path for cases where the first structured JSON
  synthesis fails but the chat model is still reachable.
- Compatibility handling for selected-file and inline-content Code Review
  payload aliases from editor integrations.
- Controlled Web Search foundation with disabled/mock providers, Tool Registry
  metadata, Project QA supplemental evidence wiring, and offline regression
  tests. The feature is disabled by default and does not require UE frontend
  changes.
- Project QA retrieval pipeline facade for RAG, local grep, optional Web Search,
  source arbitration, and retrieval quality gate composition.
- Offline Controlled Web Search eval dataset and runner covering trigger policy,
  safe-domain filtering, provider fallback, and no-network regression checks.
- Lightweight Web Memory cache with TTL, quality score, feedback API, ToolSpec
  metadata, and Project QA recall before issuing a new Web Search. Disabled by
  default and stores only URL/domain/snippet metadata.
- Retrieval source policy helpers and evidence normalizers for Project QA,
  splitting source arbitration, quality gates, warning merge, and evidence
  shaping out of the pipeline orchestrator.
- Optional Brave Web Search provider adapter and manual smoke script for local
  real-provider validation without adding network requirements to CI.
- Public v0.1.4 release note documenting the Web Evidence, Web Memory, provider
  smoke, verification, and UE frontend compatibility boundary.

### Changed

- CI now avoids live LLM, Qdrant, UE editor, eval, and integration dependencies
  on push/pull request runs.
- Requirements files are documented as compatibility shims; `pyproject.toml`
  remains the dependency source of truth.
- RAG subpackage entry points now expose public contracts instead of
  placeholder-only package files.
- Project QA local search traces now report why local grep was skipped, for
  example `disabled_by_payload` or `required_query_terms_not_found`.
- Code Review smoke documentation now explains PowerShell `Method Not Allowed`
  pitfalls and the `compact_text_retry` diagnostics path.
- Code Review benchmark report refreshed on 2026-05-12 with 20 offline cases
  passing at 1.0 recall and 1.0 precision.
- Code Review benchmark now includes known-limitation cases so the public report
  reflects both covered rule families and current lightweight-rule boundaries.
- Code Review rule coverage now detects `ConstructorHelpers::FObjectFinder`,
  `LoadClass`, missing lifecycle `Super::` calls, and delegate bindings without
  visible cleanup; the offline benchmark now reports 26 cases at 0.9355 recall
  and 1.0 precision with 2 documented known limitations.
- Project QA now consumes a stable retrieval evidence package from
  `app/rag/pipeline.py` while preserving existing response/debug fields for UE
  plugin compatibility.
- Controlled Web Search results can optionally update Web Memory when
  `WEB_MEMORY_ENABLED=true`; cached evidence remains lower priority than local
  KB/project evidence and never writes into `knowledge/`.
- `app/rag/pipeline.py` now focuses on stage orchestration, while
  `app/rag/source_policy.py` and `app/rag/evidence_normalizer.py` hold the
  reusable retrieval policy and evidence-shaping logic.
- Web Search settings now include `WEB_SEARCH_API_KEY` and
  `WEB_SEARCH_ENDPOINT`; they are only used when a real provider such as
  `brave` is explicitly selected.

## 0.1.0 - 2026-05-09

### Added

- Local FastAPI backend for UE Agent workflows.
- Five core skills: Project QA, Code Review, Code Generate, Logs Analyze, and
  Assets Inspect.
- Tool Registry, Proposal safety flow, Project Inventory, lexical/local RAG, and
  optional vector integration.
- Local benchmark and hallucination guard reports.
