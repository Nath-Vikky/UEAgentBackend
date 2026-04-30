from __future__ import annotations

from pathlib import Path

from scripts.scan_knowledge_sources import build_markdown_summary, summarize_knowledge_sources


TEST_TMP_DIR = Path(__file__).resolve().parent / ".tmp" / "knowledge-source-scan"


def test_summarize_knowledge_sources_counts_domains_without_reading_contents() -> None:
    engine_dir = TEST_TMP_DIR / "knowledge" / "engine-notes"
    code_dir = TEST_TMP_DIR / "knowledge" / "code-reference"
    engine_dir.mkdir(parents=True, exist_ok=True)
    code_dir.mkdir(parents=True, exist_ok=True)
    (engine_dir / "ue-threading.md").write_text("# UE Threading\n", encoding="utf-8")
    (code_dir / "example.cpp").write_text("// example\n", encoding="utf-8")
    (TEST_TMP_DIR / "knowledge" / "ignored.png").write_text("not supported", encoding="utf-8")

    summary = summarize_knowledge_sources(
        source_paths=[str(TEST_TMP_DIR / "knowledge"), str(TEST_TMP_DIR / "missing")],
        base_dir=Path.cwd(),
        max_file_bytes=10_000,
        include_samples=True,
        sample_limit=2,
    )

    assert summary["file_count"] == 2
    assert summary["discovered_supported_files"] == 2
    assert summary["domain_counts"]["engine_notes"] == 1
    assert summary["domain_counts"]["code_reference"] == 1
    assert summary["suffix_counts"][".md"] == 1
    assert summary["suffix_counts"][".cpp"] == 1
    assert summary["missing_sources"] == [str(TEST_TMP_DIR / "missing")]
    assert "does not copy private knowledge contents" in summary["privacy_note"]


def test_build_markdown_summary_includes_counts_and_privacy_note() -> None:
    summary = {
        "privacy_note": "metadata only",
        "source_paths": ["./knowledge"],
        "file_count": 2,
        "discovered_supported_files": 2,
        "skipped_large_file_count": 0,
        "missing_sources": [],
        "domain_counts": {"engine_notes": 1},
        "suffix_counts": {".md": 1},
        "sample_paths": {},
    }

    markdown = build_markdown_summary(summary)

    assert "# Knowledge Source Scan" in markdown
    assert "metadata only" in markdown
    assert "| `engine_notes` | 1 |" in markdown
