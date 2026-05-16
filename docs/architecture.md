# Architecture

UE Agent Backend is a local AI Agent backend for Unreal Editor workflows. The
architecture is intentionally lightweight: HTTP remains the stable integration
protocol with the UE plugin, while tools, RAG, memory, and proposals are kept
modular enough to evolve later.

## Request Flow

```text
UE Editor Plugin
  -> FastAPI Route
  -> UnifiedTaskRequest
  -> TaskService
  -> Router
  -> Context Bundle / Memory / Active Context
  -> RouteExecutionDispatcher
  -> Skill Executor or Project QA path
  -> Tool Registry
  -> Tool / RAG / Project Inventory / LLM / Proposal
  -> Self-Reflection / Decision Trace
  -> UnifiedTaskResponse
  -> UE Editor Plugin
```

## Layers

```text
API
  app/api/routes/*
  Thin HTTP layer. It sets task_type and delegates to services.

Schemas
  app/schemas/*
  Stable request/response contracts for UE frontend and tests.

Agent
  app/agent/*
  Routing, context compression, lightweight memory, controlled tool planning,
  self-reflection, and decision trace.

Memory Providers
  app/agent/memory_providers.py
  Framework-neutral adapters for memory recall. The Context Bundle currently
  uses `SessionLongTermMemoryProvider` for project/session memory while
  preserving the existing `long_term_memory` payload. `WebMemoryProvider`
  exposes cached web evidence through the same provider contract for later use.

Router Signal Detectors
  app/agent/signal_detectors.py
  Compatibility-observer layer for router signals. The existing router still
  makes final decisions, but each Agent Chat / Project QA route now records
  scored detector observations such as inventory, tool keyword, UE knowledge,
  direct command, and project context signals. This provides a safe baseline
  before any future scoring-router migration.

Skills
  app/skills/*
  User-facing capabilities: Project QA, Code Review, Code Generate,
  Logs Analyze, Assets Inspect.

Tools
  app/tools/*
  Smaller callable operations with declared input/output schemas and side
  effect levels. `app/tools/context.py` defines the normalized `ToolContext`
  and `ToolResult` envelopes used by newly migrated executors and future MCP
  transport adapters.

Services
  app/services/*
  Business orchestration for KB, LLM, Project Inventory, proposals, editor
  operations, sessions, runtime profiles, and MCP transport.

Task Handlers
  app/services/task_handlers/*
  A low-risk adapter layer for route execution. `TaskService` still owns task
  lifecycle, persistence, events, and response composition, while
  `RouteExecutionDispatcher` chooses the correct task handler. Current handlers
  call the existing execution methods first; concrete logic can move into each
  handler in later migrations. Concrete migrated handlers now include
  `DirectAnswerHandler`, `ConfigValidateHandler`, `CodeReviewHandler`,
  `LogsAnalyzeHandler`, `CodeGenerateHandler`, `ConfigGenerateHandler`, and
  `PerfAnalyzeHandler`, `AssetsInspectHandler`, `PlaceholderTaskHandler`, and
  `EditorOperationProposalHandler`, and `ProjectQAHandler`.

RAG
  app/rag/*
  Ingestion, chunking, lexical/hybrid retrieval, optional vector search,
  citations, and evaluation metrics.

Retrieval Pipeline
  app/rag/pipeline.py
  Project QA evidence orchestration: RAG -> local grep -> optional controlled
  Web Search -> source arbitration -> quality gate. The service layer consumes
  the stable evidence package instead of hand-wiring each fallback.

Retrieval Source Policy
  app/rag/source_policy.py and app/rag/evidence_normalizer.py
  Shared Project QA retrieval policy helpers. Evidence normalizers convert RAG,
  local grep, Web Memory, and Web Search outputs into the same document/citation
  shape. Source policy owns primary-source selection, quality-gate counters, and
  warning merge behavior.

Knowledge Curation
  app/rag/curation.py
  Suggestion-only KB maintenance helper. When local KB evidence is weak but Web
  Memory or controlled Web Search supplies useful evidence, it emits
  human-review candidates. It never writes to `knowledge/`, storage, or vector
  indexes automatically.

Web Search
  app/services/web_search_service.py
  Optional controlled web evidence layer. Disabled by default; mock/offline
  provider is used for tests, while the optional Brave provider is reserved for
  local smoke with an explicit API key and allow-listed domains.

Web Memory
  app/services/web_memory_service.py
  Optional local cache for controlled Web Search summaries. Disabled by default;
  stores URL/domain/snippet metadata only and never writes into the KB. SQLite
  FTS5 is used as an optional recall accelerator when available; the Python
  token scorer remains the compatibility fallback.

DB
  app/db/*
  SQLite + SQLAlchemy models and repositories for local persistence.

Evaluation
  app/evaluation/* and scripts/*
  Local regression metrics for RAG, task workflows, hallucination guards, and
  code review. Controlled Web Search has an offline policy/safety eval that
  never performs real network access.
```

## Skill vs Tool vs MCP

| Concept | Meaning In This Project |
| --- | --- |
| Skill | A user-facing workflow, such as Code Review or Logs Analyze. |
| Tool | A smaller callable operation, such as `query_project_inventory` or `analyze_ue_log`. |
| MCP | An optional future transport for tools. HTTP remains the UE plugin integration path. |

Skills compose tools. Tools declare side effects. MCP does not replace the
backend; it can become one transport under the Tool Registry.

## Tool Execution Contract

The current stable runtime still calls existing skill executors and services,
but new tool migrations should use the normalized contract in
`app/tools/context.py`:

```text
ToolSpec -> ToolContext -> executor/service -> ToolResult -> debug entry
```

`ToolContext` carries the selected `tool_id`, request payload, active context,
runtime options, trace ids, and timeout. `ToolResult` carries status, summary,
structured output, citations, artifacts, warnings, latency, and approval state.
This keeps the future executor layer framework-neutral: a tool can run through
local Python, HTTP, or MCP transport while preserving the same debug envelope.

## Optional Function Calling Adapter

`app/agent/function_calling_adapter.py` is a small compatibility layer for
future model-native tool calling. It exports selected Tool Registry entries as
provider-style function schemas, then normalizes provider tool-call payloads
back into the current `requested_tool_ids / tool_inputs_by_id` planner
contract.

This adapter is deliberately not the primary router. The stable path remains:

```text
Tool Registry -> deterministic/ReAct Lite planner -> existing Skill executor
```

Free-chat exports are read-only by default. Confirmed-write tools stay behind
the existing Proposal confirmation flow.

## Optional Graph Adapter

`app/agent/graph_adapter.py` describes the existing
`review -> fix_draft -> validate` code-review chain as a framework-neutral graph
spec. The current runtime still uses the self-contained
`ReviewFixValidateChain`; the graph spec is a small bridge for future
LangGraph-style orchestration.

The boundary is intentionally narrow:

- No LangGraph dependency is required.
- The graph spec is serializable and testable.
- `fix_draft` remains `plan_only`; it does not write files.
- Confirmed writes still require Proposal confirmation outside the graph.

## Safety Boundary

The backend does not directly mutate UE assets or project files from an LLM
answer. Write-capable operations must use:

```text
ToolSpec(side_effect_level="confirmed_write")
  -> Proposal
  -> User confirmation
  -> UE plugin executes Editor API
  -> Backend records result
```

Read operations are also bounded. Project file reads are constrained by
`project_root`, allowed extensions, and max bytes.

## RAG Boundary

The knowledge base is for stable evidence such as UE notes, code references, and
team rules. Current-project facts come from Project Inventory snapshots, not
from static KB documents.

```text
General UE knowledge -> KB/RAG/local grep
Recent controlled web summaries -> Web Memory
Fresh or explicitly requested public evidence -> Controlled Web Search
Current project facts -> Project Inventory
Selected asset facts -> UE plugin metadata + Assets Inspect
Source file details -> guarded project file read
```

Web Search is lower priority than local KB, project inventory, selected files,
and team rules. It does not write web content into the KB automatically; results
are passed as supplemental citations plus debug trace.

Project QA now goes through `app/rag/pipeline.py`:

```text
retrieve_knowledge()
  -> local grep fallback when indexed KB has no useful evidence
  -> optional Web Memory recall when local evidence is insufficient
  -> controlled Web Search only when enabled and policy says it is needed
  -> evidence normalizers
  -> source_policy.source_arbitration
  -> source_policy.retrieval_quality_gate
  -> stable response/debug fields
```

This keeps public response fields compatible while making future retrieval
stages easier to test in isolation. The source policy module is deliberately
small: it does not call LLMs, does not read files, and does not mutate storage.
That boundary lets future retrieval sources plug in without changing the UE
frontend response contract.

Web Memory has a narrower contract than the KB:

- It is disabled by default.
- It stores summaries and source metadata, not full web pages.
- It has TTL and max-entry trimming.
- Helpful/unhelpful feedback changes ranking only; it does not turn a source
  into trusted project truth.
- Local KB, project inventory, selected files, and team rules remain higher
  priority.

## Controlled Agent Loop

Project QA uses a controlled ReAct Lite planner:

```text
Thought: decide whether the question needs KB, inventory, or file context
Action: call read-only tools from the Tool Registry
Observation: collect structured results
Final: synthesize the answer or fall back to deterministic summaries
```

The planner is allowed to suggest only read-only free-chat tools. Confirmed
write tools are never executed directly from free chat.

## Evaluation

The project keeps quality checks local and reproducible:

- Unit and contract tests for CI.
- Integration tests for local backend behavior.
- RAG eval for retrieval quality.
- Hallucination guard eval for unsupported-answer behavior.
- Code review benchmark for UE C++ rules.
- Web Search eval for trigger policy, provider fallback, and safe-domain
  filtering.

CI intentionally avoids live LLM calls, UE editor dependencies, Qdrant, and
large integration/eval jobs. Those remain local commands.
