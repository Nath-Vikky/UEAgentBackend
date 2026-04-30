from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from app.i18n.language import detect_language
from app.rag.ingestion.cleaners import clean_text
from app.rag.ingestion.capabilities import CODE_SOURCE_SUFFIXES, TEXT_SOURCE_SUFFIXES
from app.rag.schemas import ParsedDocument

PROJECT_DOC_NAMES = {
    "backend.md",
    "forward.md",
    "readme.md",
    "readme.txt",
}

PROJECT_DOC_STEMS = {
    "backend",
    "forward",
    "readme",
    "architecture",
    "roadmap",
    "handoff",
}

DOMAIN_DIR_ALIASES = {
    "asset-rules": "asset_rules",
    "asset_rules": "asset_rules",
    "code-reference": "code_reference",
    "code_reference": "code_reference",
    "config-schema": "config_schema",
    "config_schema": "config_schema",
    "engine-notes": "engine_notes",
    "engine_notes": "engine_notes",
    "examples": "examples",
    "incident-history": "incident_history",
    "incident_history": "incident_history",
    "perf-notes": "perf_notes",
    "perf_notes": "perf_notes",
    "project-docs": "project_docs",
    "project_docs": "project_docs",
    "prompt-packs": "prompt_packs",
    "prompt_packs": "prompt_packs",
    "team-rules": "team_rules",
    "team_rules": "team_rules",
}

IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")


def _contains_any(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token in value for token in tokens)


def _classify_path_domain(path: Path) -> str | None:
    parts = [part.lower().replace("_", "-") for part in path.parts]
    for part in reversed(parts):
        if part in DOMAIN_DIR_ALIASES:
            return DOMAIN_DIR_ALIASES[part]
    return None


def _classify_domain(path: Path, text: str) -> str:
    path_lower = path.as_posix().lower()
    name_lower = path.name.lower()
    stem_lower = path.stem.lower()
    suffix_lower = path.suffix.lower()
    preview_lower = text[:2000].lower()
    combined = f"{path_lower} {preview_lower}"

    if suffix_lower in CODE_SOURCE_SUFFIXES or ("/source/" in path_lower and suffix_lower in TEXT_SOURCE_SUFFIXES):
        return "code_reference"

    path_domain = _classify_path_domain(path)
    if path_domain:
        return path_domain

    if _contains_any(combined, ("schema", "config", ".ini", ".json", ".yaml", ".yml", ".toml")):
        return "config_schema"
    if _contains_any(combined, ("incident", "error", "exception", "callstack", "log")):
        return "incident_history"
    if _contains_any(combined, ("perf", "memory", "insights", "memreport", "profiling")):
        return "perf_notes"
    if _contains_any(combined, ("asset", "/game/", "uasset")):
        return "asset_rules"

    # Project docs are common enough that they should win before weaker content hints.
    if name_lower in PROJECT_DOC_NAMES or stem_lower in PROJECT_DOC_STEMS or "/docs/" in path_lower:
        return "project_docs"

    if _contains_any(
        path_lower,
        (
            "/rules/",
            "/standards/",
            "style-guide",
            "style_guide",
            "coding-standard",
            "coding_standard",
            "convention",
            "naming",
            "\u89c4\u8303",
            "\u547d\u540d",
            "\u7ea6\u5b9a",
        ),
    ) or _contains_any(
        name_lower,
        (
            "rules",
            "standards",
            "style-guide",
            "style_guide",
            "convention",
            "naming",
            "\u89c4\u8303",
            "\u547d\u540d",
            "\u7ea6\u5b9a",
        ),
    ):
        return "team_rules"
    if _contains_any(combined, ("engine", "ue5", "unreal")):
        return "engine_notes"
    if _contains_any(combined, ("example", "template", "sample", "\u793a\u4f8b")):
        return "examples"
    return "project_docs"


def _classify_doc_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in CODE_SOURCE_SUFFIXES:
        return "code"
    if suffix in {".json", ".csv"}:
        return "schema"
    if suffix in {".md", ".txt", ".html"}:
        return "reference"
    if suffix in {".pdf", ".docx"}:
        return "manual"
    return "reference"


def _expand_code_identifiers(text: str) -> str:
    expanded: list[str] = []
    seen: set[str] = set()
    for match in IDENTIFIER_RE.findall(text):
        candidate = match.replace("_", " ")
        candidate = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", candidate).strip()
        lowered = candidate.lower()
        if not candidate or lowered in seen or lowered == match.lower():
            continue
        expanded.append(candidate)
        seen.add(lowered)
        if len(expanded) >= 200:
            break
    if not expanded:
        return text
    return text.strip() + "\n\n" + "\n".join(expanded)


def _parse_text_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        return json.dumps(data, ensure_ascii=False, indent=2)
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            rows = list(csv.reader(handle))
        return "\n".join([", ".join(row) for row in rows])
    return path.read_text(encoding="utf-8", errors="ignore")


def _parse_docling(path: Path) -> tuple[str, str] | None:
    try:
        from docling.document_converter import DocumentConverter
    except Exception:
        return None

    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        markdown_text = result.document.export_to_markdown()
        return markdown_text, "docling"
    except Exception:
        return None


def _parse_unstructured(path: Path) -> tuple[str, str] | None:
    try:
        from unstructured.partition.auto import partition
    except Exception:
        return None

    try:
        elements = partition(filename=str(path))
        text = "\n".join(item.text for item in elements if getattr(item, "text", "").strip())
        return text, "unstructured"
    except Exception:
        return None


def parse_path(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    parser_name = "builtin"
    if suffix in TEXT_SOURCE_SUFFIXES:
        raw_text = _parse_text_file(path)
        cleaned = clean_text(raw_text, is_html=suffix == ".html")
        if suffix in CODE_SOURCE_SUFFIXES:
            cleaned = _expand_code_identifiers(cleaned)
    else:
        parsed = _parse_docling(path) or _parse_unstructured(path)
        if not parsed:
            raise ValueError(f"Unsupported parser for {path.name}")
        raw_text, parser_name = parsed
        cleaned = clean_text(raw_text)

    title = path.stem.replace("_", " ").replace("-", " ").strip() or path.name
    language = detect_language(cleaned[:2000])
    return ParsedDocument(
        source_path=str(path),
        source_type="file",
        title=title,
        text=cleaned,
        language=language,
        parser_name=parser_name,
        doc_type=_classify_doc_type(path),
        domain=_classify_domain(path, cleaned),
        metadata={"suffix": suffix},
    )
