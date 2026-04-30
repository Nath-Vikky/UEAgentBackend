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


def test_local_search_finds_enhanced_input_character_seed() -> None:
    service = LocalSearchService(Settings(openai_api_key="", kb_source_paths=["./knowledge"]))
    result = service.search(
        query="角色增强输入代码怎么写",
        domain_filters=["code_reference", "engine_notes", "examples"],
        top_k=5,
    )

    assert result["items"]
    matched_sources = {item["source_path"] for item in result["items"]}
    assert any("enhanced-input" in source for source in matched_sources)


def test_local_search_finds_common_ue_code_generation_seeds() -> None:
    service = LocalSearchService(Settings(openai_api_key="", kb_source_paths=["./knowledge"]))
    result = service.search(
        query="射线交互 GameInstanceSubsystem 交互组件 DataAsset GameplayTag",
        domain_filters=["code_reference", "engine_notes", "examples"],
        top_k=10,
    )

    matched_sources = {item["source_path"] for item in result["items"]}
    assert any("line-trace" in source for source in matched_sources)
    assert any("subsystem" in source for source in matched_sources)
    assert any("interaction-component" in source for source in matched_sources)
    assert any("dataasset" in source.lower() for source in matched_sources)


def test_local_search_expands_chinese_engine_terms_to_english_notes() -> None:
    service = LocalSearchService(Settings(openai_api_key="", kb_source_paths=["./knowledge"]))
    result = service.search(
        query="actor的生命周期是什么",
        domain_filters=["engine_notes"],
        top_k=5,
    )

    matched_sources = {item["source_path"] for item in result["items"]}
    assert any("ue-actor-lifecycle" in source for source in matched_sources)
    assert any("lifecycle" in item["matched_terms"] for item in result["items"])


def test_local_search_finds_distilled_uecpp_course_pack() -> None:
    service = LocalSearchService(Settings(openai_api_key="", kb_source_paths=["./knowledge"]))
    result = service.search(
        query="HTTP请求 WebSocket长连接 GAS技能系统 属性同步 反射宏",
        domain_filters=["engine_notes", "examples", "code_reference", "prompt_packs"],
        top_k=10,
    )

    matched_sources = {item["source_path"] for item in result["items"]}
    assert any("uecpp-async-networking-gas" in source for source in matched_sources)
    assert any("uecpp-http-websocket" in source for source in matched_sources)
    assert any("gas-minimal-attribute-set" in source for source in matched_sources)
    assert any("ue-cpp-practices" in source for source in matched_sources)


def test_local_search_status_reports_prompt_pack_domain() -> None:
    service = LocalSearchService(Settings(openai_api_key="", kb_source_paths=["./knowledge"]))
    status = service.status()

    assert status["domain_counts"]["prompt_packs"] >= 1
