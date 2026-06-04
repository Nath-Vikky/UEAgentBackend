from __future__ import annotations

import importlib.util

TEXT_SOURCE_SUFFIXES = {
    ".md",
    ".txt",
    ".html",
    ".json",
    ".csv",
    ".h",
    ".hpp",
    ".hh",
    ".inl",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".cs",
    ".py",
    ".ini",
    ".cfg",
}

CODE_SOURCE_SUFFIXES = {
    ".h",
    ".hpp",
    ".hh",
    ".inl",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".cs",
    ".py",
}

DOCUMENT_SOURCE_SUFFIXES = {".pdf", ".docx"}
SUPPORTED_SUFFIXES = TEXT_SOURCE_SUFFIXES | DOCUMENT_SOURCE_SUFFIXES

KNOWLEDGE_DOMAINS = [
    "project_docs",
    "code_reference",
    "examples",
    "team_rules",
    "asset_rules",
    "blueprint_umg",
    "engine_notes",
    "troubleshooting",
    "incident_history",
    "perf_notes",
    "config_schema",
    "prompt_packs",
]

INGESTION_PIPELINE = [
    "loader",
    "parser",
    "cleaner",
    "chunker",
    "lexical_index",
    "embedding",
    "vector_store",
    "retrieval",
]


def _strip_dot(suffixes: set[str]) -> list[str]:
    return sorted(suffix.lstrip(".") for suffix in suffixes)


def _module_status(module_name: str) -> str:
    return "available" if importlib.util.find_spec(module_name) else "missing"


def parser_dependency_status() -> dict[str, str]:
    return {
        "builtin_text_code_html": "available",
        "docling": _module_status("docling"),
        "unstructured": _module_status("unstructured"),
    }


def ingestion_capabilities() -> dict[str, object]:
    return {
        "pipeline": INGESTION_PIPELINE,
        "format_groups": {
            "text": _strip_dot(TEXT_SOURCE_SUFFIXES - CODE_SOURCE_SUFFIXES - {".html"}),
            "code": _strip_dot(CODE_SOURCE_SUFFIXES),
            "html": ["html"],
            "documents": _strip_dot(DOCUMENT_SOURCE_SUFFIXES),
        },
        "supported_formats": _strip_dot(SUPPORTED_SUFFIXES),
        "first_class_formats": _strip_dot(TEXT_SOURCE_SUFFIXES),
        "enhanced_formats": _strip_dot(DOCUMENT_SOURCE_SUFFIXES),
        "parser_dependencies": parser_dependency_status(),
        "knowledge_domains": KNOWLEDGE_DOMAINS,
    }
