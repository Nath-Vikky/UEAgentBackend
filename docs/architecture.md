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

Skills
  app/skills/*
  User-facing capabilities: Project QA, Code Review, Code Generate,
  Logs Analyze, Assets Inspect.

Tools
  app/tools/*
  Smaller callable operations with declared input/output schemas and side
  effect levels.

Services
  app/services/*
  Business orchestration for KB, LLM, Project Inventory, proposals, editor
  operations, sessions, runtime profiles, and MCP transport.

RAG
  app/rag/*
  Ingestion, chunking, lexical/hybrid retrieval, optional vector search,
  citations, and evaluation metrics.

DB
  app/db/*
  SQLite + SQLAlchemy models and repositories for local persistence.

Evaluation
  app/evaluation/* and scripts/*
  Local regression metrics for RAG, task workflows, hallucination guards, and
  code review.
```

## Skill vs Tool vs MCP

| Concept | Meaning In This Project |
| --- | --- |
| Skill | A user-facing workflow, such as Code Review or Logs Analyze. |
| Tool | A smaller callable operation, such as `query_project_inventory` or `analyze_ue_log`. |
| MCP | An optional future transport for tools. HTTP remains the UE plugin integration path. |

Skills compose tools. Tools declare side effects. MCP does not replace the
backend; it can become one transport under the Tool Registry.

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
Current project facts -> Project Inventory
Selected asset facts -> UE plugin metadata + Assets Inspect
Source file details -> guarded project file read
```

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

CI intentionally avoids live LLM calls, UE editor dependencies, Qdrant, and
large integration/eval jobs. Those remain local commands.
