# Changelog

This project follows a lightweight changelog style inspired by Keep a
Changelog. Dates use `YYYY-MM-DD`.

## Unreleased

### Added

- RAG facade, reusable workflow nodes, and an in-process ingestion job queue.
- Integration smoke test guide for the main HTTP workflows.
- Controlled Project QA tool planner module and tool-call sequence debug output.
- Project Inventory field views for focused asset/code metadata answers.
- Bounded log-analysis ReAct debug trace.
- Lightweight CI for Ruff plus unit/contract tests.
- Public architecture and contribution docs.

### Changed

- CI now avoids live LLM, Qdrant, UE editor, eval, and integration dependencies
  on push/pull request runs.
- Requirements files are documented as compatibility shims; `pyproject.toml`
  remains the dependency source of truth.

## 0.1.0 - 2026-05-09

### Added

- Local FastAPI backend for UE Agent workflows.
- Five core skills: Project QA, Code Review, Code Generate, Logs Analyze, and
  Assets Inspect.
- Tool Registry, Proposal safety flow, Project Inventory, lexical/local RAG, and
  optional vector integration.
- Local benchmark and hallucination guard reports.
