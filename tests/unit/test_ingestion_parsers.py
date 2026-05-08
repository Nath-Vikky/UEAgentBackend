import shutil
import uuid
from pathlib import Path

from app.rag.ingestion.parsers import parse_path


def _runtime_root(name: str) -> Path:
    return Path(".test-runtime") / f"{name}-{uuid.uuid4().hex}"


def test_parse_path_prefers_knowledge_domain_directory_over_content_keywords() -> None:
    runtime_root = _runtime_root("parser-domain")
    examples_dir = runtime_root / "knowledge" / "examples"
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        examples_dir.mkdir(parents=True)
        note = examples_dir / "developer-settings-subsystem-note.md"
        note.write_text(
            "# Developer Settings Example\n\nconfig schema log error words should not override examples.",
            encoding="utf-8",
        )

        parsed = parse_path(note)

        assert parsed.domain == "examples"
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def test_parse_path_recognizes_prompt_pack_domain() -> None:
    runtime_root = _runtime_root("parser-prompt-pack")
    prompt_dir = runtime_root / "knowledge" / "prompt-packs"
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        prompt_dir.mkdir(parents=True)
        prompt_pack = prompt_dir / "ue-cpp-practices.md"
        prompt_pack.write_text(
            "# Prompt Pack\n\nconfig and schema guidance for LLM behavior.",
            encoding="utf-8",
        )

        parsed = parse_path(prompt_pack)

        assert parsed.domain == "prompt_packs"
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def test_parse_path_keeps_public_docs_as_project_docs_even_with_config_keywords() -> None:
    runtime_root = _runtime_root("parser-project-docs")
    docs_dir = runtime_root / "docs"
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        docs_dir.mkdir(parents=True)
        guide = docs_dir / "backend-user-guide.md"
        guide.write_text(
            "# Backend User Guide\n\n"
            "This public guide explains KB_SOURCE_PATHS, config, schema, JSON, env, "
            "chunk sizing, logs, and benchmark settings for users.",
            encoding="utf-8",
        )

        parsed = parse_path(guide)

        assert parsed.domain == "project_docs"
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def test_parse_path_keeps_explicit_config_schema_directory() -> None:
    runtime_root = _runtime_root("parser-config-schema")
    schema_dir = runtime_root / "knowledge" / "config-schema"
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        schema_dir.mkdir(parents=True)
        schema = schema_dir / "gameplay-config.md"
        schema.write_text("# Gameplay Config\n\nProject docs words should not override this explicit directory.", encoding="utf-8")

        parsed = parse_path(schema)

        assert parsed.domain == "config_schema"
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)
