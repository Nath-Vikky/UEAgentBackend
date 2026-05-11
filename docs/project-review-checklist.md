# Project Review Checklist

This checklist is for keeping UE Agent Backend clean as an open-source local Agent project. It is intentionally small: the goal is a stable, explainable local Agent backend, not an enterprise platform.

## Release Readiness

- `README.md` explains the project as a local UE Agent backend, not a generic chatbot.
- Public docs are limited to user-facing material: `README.md`, `docs/backend-user-guide.md`, eval reports, release notes, and this checklist.
- Local process docs remain ignored by Git, including dev logs, frontend handoff notes, and improvement plans.
- `.env` and private knowledge sources are never committed.
- `KB_SOURCE_PATHS` defaults to `./knowledge`.
- `EMBEDDING_ENABLED` defaults to `false` so lexical RAG works without Qdrant or an embedding model.

## Architecture Checks

- Five core features remain the public scope: Agent Chat / Project QA, Code Review, Code Generate, Logs Analyze, Assets Inspect.
- Deferred compatibility tasks stay hidden from the main frontend menu.
- Explicit panels use fixed built-in Skills before any LLM free-form tool choice.
- Agent Chat may auto-select only read-only tools from the Tool Registry whitelist.
- Write-capable tools must use Proposal confirmation and backend safety checks.
- MCP remains an optional backend tool transport; HTTP remains the UE frontend/backend protocol.
- RAG package entry points expose real public contracts rather than placeholder-only modules.
- Unused service placeholders should be deleted instead of kept for future speculation.

## Verification Commands

Run before tagging or presenting the project:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract tests\eval
.\.venv\Scripts\python.exe -m pytest tests\integration
.\.venv\Scripts\python.exe scripts\run_hallucination_eval.py --source-path .\README.md --source-path .\docs --source-path .\knowledge --min-grounding-accuracy 1.0 --max-unsupported-answer-rate 0.0 --output storage\artifacts\evals\hallucination-guard-latest.json --markdown-output docs\hallucination-guard-report.md
rg -n "placeholder|not implemented|NotImplemented|raise NotImplementedError" app
```

If `make` is available:

```powershell
make review
make benchmark
make hallucination-eval
```

## Demo Checklist

- Backend starts with `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
- `GET /api/v1/system/health` returns no blocking startup errors.
- `GET /api/v1/system/capabilities` shows Skill Catalog, Tool Protocol v2, MCP adapter status, and evaluation report capability.
- `POST /api/v1/knowledge-base/reindex` succeeds with the default `./knowledge` source.
- Code Generate can answer a UE C++ prompt using local code references.
- Code Review can scan and review one selected `.h/.cpp/.cs` file.
- Project Inventory snapshot can be submitted from the UE plugin Debug View.
- Agent Chat can answer project inventory questions after a snapshot is submitted.
- Eval reports are readable through `GET /api/v1/knowledge-base/eval/reports`.
- Hallucination guard report shows `grounding_accuracy=1.0` and `unsupported_answer_rate=0.0` for the stable local dataset.

## Known Non-Goals

- No cloud deployment, user management, billing, or enterprise observability platform.
- No fully automatic modification of UE projects.
- No dynamic plugin marketplace or runtime skill installation.
- No commitment to cover every Unreal Engine API.
- No redistribution of private course material or third-party knowledge bases.

## Next Maintenance Targets

- Split the large integration test file by feature area.
- Gradually thin `TaskService` into smaller route execution collaborators.
- Add a lightweight cleanup script for local test/runtime artifacts if Windows ACLs allow it.
