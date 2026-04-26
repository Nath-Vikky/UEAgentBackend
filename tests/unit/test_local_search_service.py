import shutil
import uuid
from pathlib import Path

from app.core.settings import Settings
from app.services.local_search_service import LocalSearchService


def _runtime_root(name: str) -> Path:
    return Path(".test-runtime") / f"{name}-{uuid.uuid4().hex}"


def test_local_search_filters_domains_and_returns_snippet() -> None:
    runtime_root = _runtime_root("local-search")
    engine_notes = runtime_root / "engine-notes"
    code_reference = runtime_root / "code-reference"
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        engine_notes.mkdir(parents=True)
        code_reference.mkdir(parents=True)
        (engine_notes / "ue-soft-references.md").write_text(
            "# Soft References\n\nUse TSoftObjectPtr and async loading instead of LoadObject in Tick.",
            encoding="utf-8",
        )
        (code_reference / "ActorExample.cpp").write_text(
            "void AExampleActor::BeginPlay() { RefreshInteractionState(); }",
            encoding="utf-8",
        )

        service = LocalSearchService(
            Settings(
                openai_api_key="",
                kb_source_paths=[str(runtime_root)],
                kb_max_file_bytes=500_000,
            )
        )
        result = service.search(
            query="TSoftObjectPtr async loading",
            domain_filters=["engine_notes"],
            top_k=3,
        )

        assert result["status"] == "completed"
        assert result["items"]
        assert result["items"][0]["domain"] == "engine_notes"
        assert result["items"][0]["source_path"].endswith("ue-soft-references.md")
        assert "TSoftObjectPtr" in result["items"][0]["snippet"]
        assert "tsoftobjectptr" in result["items"][0]["matched_terms"]
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def test_local_search_status_reports_domain_counts() -> None:
    runtime_root = _runtime_root("local-search-status")
    asset_rules = runtime_root / "asset-rules"
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        asset_rules.mkdir(parents=True)
        (asset_rules / "blueprint-checklist.md").write_text(
            "# Blueprint Checklist\n\nCheck Tick, parent class, dependencies, and naming.",
            encoding="utf-8",
        )

        service = LocalSearchService(Settings(openai_api_key="", kb_source_paths=[str(runtime_root)]))
        status = service.status()

        assert status["status"] == "ready"
        assert status["searchable_files"] == 1
        assert status["domain_counts"]["asset_rules"] == 1
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)
