from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.rag.ingestion.capabilities import SUPPORTED_SUFFIXES
from app.rag.schemas import resolve_local_path
from app.services.local_search_service import _infer_domain


def discover_supported_files(source_paths: list[str], *, base_dir: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    missing_sources: list[str] = []
    for raw_path in source_paths:
        candidate = resolve_local_path(raw_path, base_dir)
        if candidate.is_dir():
            files.extend(
                file_path.resolve()
                for file_path in candidate.rglob("*")
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_SUFFIXES
            )
        elif candidate.is_file() and candidate.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(candidate.resolve())
        else:
            missing_sources.append(raw_path)
    return (sorted(dict.fromkeys(files)), missing_sources)


def summarize_knowledge_sources(
    *,
    source_paths: list[str],
    base_dir: Path,
    max_file_bytes: int,
    include_samples: bool = False,
    sample_limit: int = 5,
) -> dict[str, Any]:
    files, missing_sources = discover_supported_files(source_paths, base_dir=base_dir)
    domain_counts: Counter[str] = Counter()
    suffix_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    skipped_large_files: list[str] = []
    sample_paths: dict[str, list[str]] = defaultdict(list)

    for file_path in files:
        size = file_path.stat().st_size
        if size > max_file_bytes:
            skipped_large_files.append(_display_path(file_path, base_dir))
            continue
        domain = _infer_domain(file_path)
        domain_counts[domain] += 1
        suffix_counts[file_path.suffix.lower() or "(none)"] += 1
        source_root = _source_root_label(file_path, source_paths=source_paths, base_dir=base_dir)
        source_counts[source_root] += 1
        if include_samples and len(sample_paths[domain]) < sample_limit:
            sample_paths[domain].append(_display_path(file_path, base_dir))

    return {
        "source_paths": source_paths,
        "base_dir": base_dir.resolve().as_posix(),
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        "file_count": sum(domain_counts.values()),
        "discovered_supported_files": len(files),
        "skipped_large_file_count": len(skipped_large_files),
        "missing_sources": missing_sources,
        "domain_counts": dict(sorted(domain_counts.items())),
        "suffix_counts": dict(sorted(suffix_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "sample_paths": dict(sample_paths) if include_samples else {},
        "privacy_note": (
            "This report reads only path, suffix, domain, and size metadata. "
            "It does not copy private knowledge contents into the repository."
        ),
    }


def build_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Knowledge Source Scan",
        "",
        summary["privacy_note"],
        "",
        "## Sources",
        "",
    ]
    for source in summary["source_paths"]:
        lines.append(f"- `{source}`")

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Indexed-size file count: `{summary['file_count']}`",
            f"- Discovered supported files: `{summary['discovered_supported_files']}`",
            f"- Skipped large files: `{summary['skipped_large_file_count']}`",
            f"- Missing sources: `{len(summary['missing_sources'])}`",
            "",
            "## Domain Counts",
            "",
            "| Domain | Files |",
            "| --- | ---: |",
        ]
    )
    for domain, count in summary["domain_counts"].items():
        lines.append(f"| `{domain}` | {count} |")

    lines.extend(["", "## Suffix Counts", "", "| Suffix | Files |", "| --- | ---: |"])
    for suffix, count in summary["suffix_counts"].items():
        lines.append(f"| `{suffix}` | {count} |")

    if summary["missing_sources"]:
        lines.extend(["", "## Missing Sources", ""])
        for source in summary["missing_sources"]:
            lines.append(f"- `{source}`")

    if summary["sample_paths"]:
        lines.extend(["", "## Optional Samples", ""])
        for domain, paths in summary["sample_paths"].items():
            lines.append(f"### `{domain}`")
            lines.extend(f"- `{path}`" for path in paths)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _display_path(path: Path, base_dir: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _source_root_label(path: Path, *, source_paths: list[str], base_dir: Path) -> str:
    resolved_path = path.resolve()
    for source in source_paths:
        candidate = resolve_local_path(source, base_dir)
        if candidate.is_file() and resolved_path == candidate.resolve():
            return source
        if candidate.is_dir():
            try:
                resolved_path.relative_to(candidate.resolve())
            except ValueError:
                continue
            return source
    return "(unknown)"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan public and local-private knowledge sources without copying file contents."
    )
    parser.add_argument(
        "--source-path",
        action="append",
        dest="source_paths",
        help="Knowledge source path. Can be repeated. Defaults to KB_SOURCE_PATHS from .env.",
    )
    parser.add_argument("--json-output", help="Optional JSON output path.")
    parser.add_argument("--markdown-output", help="Optional Markdown output path.")
    parser.add_argument("--max-file-bytes", type=int, default=None)
    parser.add_argument("--include-samples", action="store_true", help="Include a few sample paths per domain.")
    parser.add_argument("--sample-limit", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = Settings()
    source_paths = args.source_paths or settings.kb_source_paths
    max_file_bytes = args.max_file_bytes or settings.kb_max_file_bytes
    summary = summarize_knowledge_sources(
        source_paths=source_paths,
        base_dir=Path.cwd(),
        max_file_bytes=max_file_bytes,
        include_samples=args.include_samples,
        sample_limit=args.sample_limit,
    )

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_output:
        output_path = Path(args.markdown_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(build_markdown_summary(summary), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["missing_sources"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
