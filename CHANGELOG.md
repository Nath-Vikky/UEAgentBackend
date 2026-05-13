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

## 0.1.0 - 2026-05-09

### Added

- Local FastAPI backend for UE Agent workflows.
- Five core skills: Project QA, Code Review, Code Generate, Logs Analyze, and
  Assets Inspect.
- Tool Registry, Proposal safety flow, Project Inventory, lexical/local RAG, and
  optional vector integration.
- Local benchmark and hallucination guard reports.
