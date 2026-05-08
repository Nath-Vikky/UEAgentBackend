from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.core.settings import Settings
from app.rag.ingestion.loaders import discover_source_paths


def _runtime_root(name: str) -> Path:
    return Path(".test-runtime") / f"{name}-{uuid.uuid4().hex}"


def test_discover_source_paths_skips_local_only_docs_during_directory_scan() -> None:
    runtime_root = _runtime_root("loader-local-docs")
    docs_dir = runtime_root / "docs"
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        docs_dir.mkdir(parents=True)
        public_guide = docs_dir / "backend-user-guide.md"
        local_plan = docs_dir / "improveplan.md"
        public_guide.write_text("# User Guide\n\nPublic project docs.", encoding="utf-8")
        local_plan.write_text("# Improve Plan\n\nLocal-only planning notes.", encoding="utf-8")

        files = discover_source_paths(
            Settings(openai_api_key="", kb_source_paths=[str(docs_dir)]),
        )
        names = {path.name for path in files}

        assert "backend-user-guide.md" in names
        assert "improveplan.md" not in names
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def test_discover_source_paths_allows_explicit_local_only_file() -> None:
    runtime_root = _runtime_root("loader-explicit-local-doc")
    docs_dir = runtime_root / "docs"
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        docs_dir.mkdir(parents=True)
        local_plan = docs_dir / "improveplan.md"
        local_plan.write_text("# Improve Plan\n\nExplicitly selected local notes.", encoding="utf-8")

        files = discover_source_paths(
            Settings(openai_api_key="", kb_source_paths=[str(local_plan)]),
        )

        assert [path.name for path in files] == ["improveplan.md"]
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)
