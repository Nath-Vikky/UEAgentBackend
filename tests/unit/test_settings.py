from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.core.settings import Settings


TEST_TMP_DIR = Path("storage/test-tmp/settings")
LIST_ENV_KEYS = (
    "APP_CORS_ORIGINS",
    "KB_SOURCE_PATHS",
    "WEB_SEARCH_ALLOWED_DOMAINS",
    "WEB_SEARCH_DOMAIN_BOOSTS",
)


@pytest.fixture
def clean_list_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in LIST_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_env_file(name: str, content: str) -> Path:
    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    env_file = TEST_TMP_DIR / f"{uuid.uuid4().hex}-{name}"
    env_file.write_text(content, encoding="utf-8")
    return env_file


def test_settings_accept_single_quoted_json_for_cors(clean_list_env: None) -> None:
    env_file = _write_env_file(
        "cors-single-quoted.env",
        "APP_CORS_ORIGINS='[\"http://localhost:3000\",\"http://127.0.0.1:3000\"]'\n"
    )
    settings = Settings(_env_file=env_file)

    assert settings.app_cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_settings_accept_csv_for_list_fields(clean_list_env: None) -> None:
    env_file = _write_env_file(
        "csv-lists.env",
        "\n".join(
            [
                "APP_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000",
                "KB_SOURCE_PATHS=../backend.md,../forward.md,./docs",
            ]
        )
    )
    settings = Settings(_env_file=env_file)

    assert settings.app_cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert settings.kb_source_paths == ["../backend.md", "../forward.md", "./docs"]


def test_settings_default_to_lexical_first_rag() -> None:
    settings = Settings(_env_file=None)

    assert settings.embedding_enabled is False
    assert settings.rag_fallback_mode == "lexical_only"
    assert settings.web_search_enabled is False
    assert settings.web_search_provider == "disabled"
    assert settings.agent_graph_framework == "framework_neutral"
    assert settings.local_memory_enabled is False
    assert settings.local_memory_root == "./runtime/memory"


def test_settings_accept_agent_graph_framework_override(clean_list_env: None) -> None:
    env_file = _write_env_file(
        "agent-framework.env",
        "AGENT_GRAPH_FRAMEWORK=langgraph_optional\n",
    )
    settings = Settings(_env_file=env_file)

    assert settings.agent_graph_framework == "langgraph_optional"


def test_settings_accept_csv_for_web_search_list_fields(clean_list_env: None) -> None:
    env_file = _write_env_file(
        "web-search-lists.env",
        "\n".join(
            [
                "WEB_SEARCH_ALLOWED_DOMAINS=dev.epicgames.com,docs.unrealengine.com",
                "WEB_SEARCH_DOMAIN_BOOSTS=dev.epicgames.com:0.25,docs.unrealengine.com:0.20",
            ]
        ),
    )
    settings = Settings(_env_file=env_file)

    assert settings.web_search_allowed_domains == ["dev.epicgames.com", "docs.unrealengine.com"]
    assert settings.web_search_domain_boosts == [
        "dev.epicgames.com:0.25",
        "docs.unrealengine.com:0.20",
    ]
