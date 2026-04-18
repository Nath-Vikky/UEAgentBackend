from __future__ import annotations

from pathlib import Path
from app.core.settings import Settings


TEST_TMP_DIR = Path(__file__).resolve().parent / ".tmp"


def _write_env_file(name: str, content: str) -> Path:
    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    env_file = TEST_TMP_DIR / name
    env_file.write_text(content, encoding="utf-8")
    return env_file


def test_settings_accept_single_quoted_json_for_cors() -> None:
    env_file = _write_env_file(
        "cors-single-quoted.env",
        "APP_CORS_ORIGINS='[\"http://localhost:3000\",\"http://127.0.0.1:3000\"]'\n"
    )
    settings = Settings(_env_file=env_file)

    assert settings.app_cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_settings_accept_csv_for_list_fields() -> None:
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
