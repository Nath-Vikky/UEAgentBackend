# Contributing

Thanks for taking a look at UE Agent Backend. The project is designed as a
local Unreal Editor Agent backend, so contribution rules favor small,
reviewable changes over broad platform work.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Checks

Fast checks used by CI:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q
```

Broader local checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract tests\eval tests\integration
.\.venv\Scripts\python.exe scripts\run_project_benchmark.py --output storage\artifacts\evals\project-benchmark-latest.json --markdown-output storage\artifacts\evals\project-benchmark-latest.md
```

## Adding A Tool

1. Add a `ToolSpec` in `app/tools/registry.py`.
2. Set `side_effect_level`, `permission_gate`, `input_schema`, and `output_schema`.
3. Implement the local executor or service method.
4. Connect it through the relevant Skill executor or Project QA tool planner.
5. Add unit tests for schema and execution behavior.
6. Update user docs if the response contract changes.

Write tools as `read_only` by default. Any editor/project write must use a
Proposal and require user confirmation.

## Adding An Editor Operation

Editor operations are confirmed-write tools that are planned by the backend and
executed by UEAgentTool after user confirmation.

1. Add or update `OPERATION_SPECS` in `app/services/editor_operation_service.py`.
2. Add payload normalization and result contract fields.
3. Add or update the UEAgentTool executor in the plugin repository.
4. Add backend integration tests for proposal creation, result handling, and
   capabilities metadata.
5. Run the catalog exporter:

```powershell
.\.venv\Scripts\python.exe scripts\export_editor_operation_catalog.py --output docs\editor-operation-catalog.md
```

6. Update user docs or frontend handoff notes if the UI contract changes.

## Adding A Skill

1. Add a `BuiltInSkillSpec` in `app/skills/registry.py`.
2. Create an executor under `app/skills/executors/`.
3. Route the explicit task in `TaskService`.
4. Reuse existing tools where possible.
5. Add tests and update `docs/backend-user-guide.md`.

Skills are user-facing capabilities. Tools are smaller callable operations.
Keep that boundary clear.

## Knowledge Base Changes

Public knowledge under `knowledge/` should be original, concise, and safe to
publish. External course notes or private documents should be connected locally
with `KB_SOURCE_PATHS`; do not copy private third-party material into the public
repository.

After adding knowledge, run:

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_eval.py --source-path .\README.md --source-path .\docs --source-path .\knowledge --top-k 4 --min-hit-at-k 0.25 --min-route-accuracy 0.75
```

## Pull Request Guidelines

- Keep PRs focused on one feature, bug fix, or doc improvement.
- Include tests for behavior changes.
- Do not commit `.env`, `storage/`, `.test-runtime/`, private docs, or external
  knowledge repositories.
- Keep public documentation focused on `README.md`, `CONTRIBUTING.md`,
  `docs/backend-user-guide.md`, and `docs/release-notes/`.
