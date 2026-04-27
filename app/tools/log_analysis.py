from __future__ import annotations

from pathlib import Path
import re
from typing import Any

TIMESTAMP_RE = re.compile(r"\[\d{4}\.\d{2}\.\d{2}[-:.\d]*\]")
CALLSTACK_RE = re.compile(r"(?:0x[0-9A-Fa-f]+|!|Callstack)")
MODULE_RE = re.compile(r"\bLog([A-Za-z0-9_]+):")
RESOURCE_RE = re.compile(r"(/Game/[A-Za-z0-9_./-]+)")

DEFAULT_LOG_MAX_CHARS = 120_000
DEFAULT_ATTACHMENT_MAX_CHARS = 30_000
LOG_TEXT_KEYS = ("log_text", "selected_log_text", "log_excerpt", "error_excerpt", "build_log", "crash_text")
LOG_FILE_KEYS = ("log_file_path", "log_path", "file_path")
ALLOWED_LOG_EXTENSIONS = {".log", ".txt", ".crashcontext", ".xml", ".json", ".ini"}

ISSUE_PATTERNS = {
    "access_violation": {
        "tokens": ("access violation", "null pointer", "read access violation"),
        "summary": "Crash-like memory access signal detected.",
        "suggestion": "Inspect object lifetime and null checks around the failing path.",
    },
    "asset_load_failure": {
        "tokens": ("failed to load", "can't find file", "missing package"),
        "summary": "Asset or package loading failure detected.",
        "suggestion": "Verify the referenced path, cooking state, and redirectors.",
    },
    "ensure_or_assert": {
        "tokens": ("ensure(", "assert", "checkf", "fatal error"),
        "summary": "Invariant failure detected.",
        "suggestion": "Review the violated assumption and reproduce with the same input set.",
    },
    "out_of_memory": {
        "tokens": ("out of memory", "oom", "memory exhausted"),
        "summary": "Memory pressure signal detected.",
        "suggestion": "Inspect peak allocations, asset residency, and streaming behavior.",
    },
    "shader_or_compile": {
        "tokens": ("shader", "compile", "link error"),
        "summary": "Compilation or shader pipeline issue detected.",
        "suggestion": "Review the first compiler error and the affected shader or module definitions.",
    },
}


def _stringify_log_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if str(item).strip())
    return str(value)


def _looks_like_path(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    return "\\" in lowered or "/" in lowered or any(lowered.endswith(suffix) for suffix in ALLOWED_LOG_EXTENSIONS)


def _candidate_paths(
    payload: dict[str, Any],
    *,
    project_root: str | None,
    context_current_file: str | None,
) -> list[str]:
    candidates: list[str] = []
    for key in LOG_FILE_KEYS:
        value = str(payload.get(key) or "").strip()
        if value:
            candidates.append(value)
    log_source = str(payload.get("log_source") or "").strip()
    if log_source and _looks_like_path(log_source):
        candidates.append(log_source)
    if context_current_file and _looks_like_path(context_current_file):
        candidates.append(context_current_file)

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        marker = candidate.casefold()
        if marker not in seen:
            unique.append(candidate)
            seen.add(marker)
    return unique


def _resolve_path(candidate: str, *, project_root: str | None) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    if project_root:
        return Path(project_root) / path
    return path


def _normalize_line_window(value: Any) -> tuple[int | None, int | None]:
    if not isinstance(value, dict):
        return None, None
    try:
        start = int(value.get("start")) if value.get("start") is not None else None
        end = int(value.get("end")) if value.get("end") is not None else None
    except (TypeError, ValueError):
        return None, None
    if start is not None and start < 1:
        start = 1
    if end is not None and start is not None and end < start:
        end = start
    return start, end


def _read_log_file(
    path: Path,
    *,
    line_window: dict[str, Any],
    max_chars: int,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "requested_path": str(path),
        "resolved_path": str(path.resolve()) if path.exists() else str(path),
        "read_status": "pending",
        "read_error": None,
        "bytes_total": None,
        "bytes_read": 0,
        "truncated": False,
        "line_window_applied": False,
    }
    if path.suffix.lower() not in ALLOWED_LOG_EXTENSIONS:
        diagnostics["read_status"] = "skipped"
        diagnostics["read_error"] = f"unsupported_extension:{path.suffix.lower() or 'none'}"
        return {"text": "", "diagnostics": diagnostics}
    if not path.exists() or not path.is_file():
        diagnostics["read_status"] = "error"
        diagnostics["read_error"] = "file_not_found"
        return {"text": "", "diagnostics": diagnostics}

    try:
        size = path.stat().st_size
        diagnostics["bytes_total"] = size
        start, end = _normalize_line_window(line_window)
        if start is not None or end is not None:
            selected: list[str] = []
            line_no = 0
            effective_start = start or 1
            effective_end = end or effective_start + 500
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line_no += 1
                    if line_no < effective_start:
                        continue
                    if line_no > effective_end:
                        break
                    selected.append(line.rstrip("\n"))
                    if sum(len(item) + 1 for item in selected) >= max_chars:
                        diagnostics["truncated"] = True
                        break
            text = "\n".join(selected).strip()
            diagnostics["read_status"] = "completed"
            diagnostics["line_window_applied"] = True
            diagnostics["line_window"] = {"start": effective_start, "end": effective_end}
            diagnostics["bytes_read"] = len(text.encode("utf-8", errors="replace"))
            return {"text": text, "diagnostics": diagnostics}

        max_bytes = max(max_chars * 2, 4096)
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(max(0, size - max_bytes))
                raw = handle.read(max_bytes)
                diagnostics["truncated"] = True
                diagnostics["tail_read"] = True
            else:
                raw = handle.read()
                diagnostics["tail_read"] = False
        text = raw.decode("utf-8", errors="replace")[-max_chars:].strip()
        diagnostics["read_status"] = "completed"
        diagnostics["bytes_read"] = len(raw)
        return {"text": text, "diagnostics": diagnostics}
    except OSError as exc:
        diagnostics["read_status"] = "error"
        diagnostics["read_error"] = exc.__class__.__name__
        return {"text": "", "diagnostics": diagnostics}


def _attachment_paths(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw_paths = payload.get("attachment_paths") or []
    if isinstance(raw_paths, str):
        values.append(raw_paths)
    elif isinstance(raw_paths, list):
        values.extend(str(item) for item in raw_paths if str(item).strip())

    raw_attachments = payload.get("attachments") or []
    if isinstance(raw_attachments, list):
        for item in raw_attachments:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                for key in ("path", "file_path", "log_file_path", "source"):
                    candidate = str(item.get(key) or "").strip()
                    if candidate:
                        values.append(candidate)
                        break
    return values[:5]


def _collect_log_input(
    payload: dict[str, Any],
    *,
    project_root: str | None,
    context_current_file: str | None,
) -> dict[str, Any]:
    line_window = payload.get("line_window") or {}
    try:
        max_chars = int(payload.get("max_chars") or DEFAULT_LOG_MAX_CHARS)
    except (TypeError, ValueError):
        max_chars = DEFAULT_LOG_MAX_CHARS
    max_chars = max(1_000, min(max_chars, DEFAULT_LOG_MAX_CHARS))
    text_parts = [
        _stringify_log_value(payload.get(key)).strip()
        for key in LOG_TEXT_KEYS
        if _stringify_log_value(payload.get(key)).strip()
    ]
    error_lines = _stringify_log_value(payload.get("error_lines")).strip()
    if error_lines:
        text_parts.append(error_lines)

    candidates = _candidate_paths(
        payload,
        project_root=project_root,
        context_current_file=context_current_file,
    )
    read_diagnostics: list[dict[str, Any]] = []
    file_text = ""
    input_mode = "pasted_text" if text_parts else "empty"
    should_read_file = not text_parts or bool(payload.get("include_file_context"))
    if should_read_file:
        for candidate in candidates:
            read_result = _read_log_file(
                _resolve_path(candidate, project_root=project_root),
                line_window=line_window,
                max_chars=max_chars,
            )
            read_diagnostics.append(read_result["diagnostics"])
            if read_result["text"]:
                file_text = read_result["text"]
                input_mode = "file_line_window" if read_result["diagnostics"].get("line_window_applied") else "file_tail"
                break
    if file_text:
        text_parts.append(file_text)

    attachment_summaries: list[dict[str, Any]] = []
    attachment_texts: list[str] = []
    for attachment in _attachment_paths(payload):
        read_result = _read_log_file(
            _resolve_path(attachment, project_root=project_root),
            line_window={},
            max_chars=DEFAULT_ATTACHMENT_MAX_CHARS,
        )
        diagnostics = read_result["diagnostics"]
        attachment_summaries.append(diagnostics)
        if read_result["text"]:
            attachment_texts.append(f"[Attachment: {attachment}]\n{read_result['text']}")
    if attachment_texts:
        text_parts.extend(attachment_texts)
        if input_mode == "empty":
            input_mode = "attachment_text"

    raw_text = "\n".join(part for part in text_parts if part).strip()
    log_source = str(payload.get("log_source") or (candidates[0] if candidates else "")).strip()
    return {
        "text": raw_text,
        "input_context": {
            "log_source": log_source,
            "log_file_path": candidates[0] if candidates else "",
            "input_mode": input_mode,
            "text_field_count": len(text_parts),
            "read_diagnostics": read_diagnostics,
            "attachment_diagnostics": attachment_summaries,
            "notes": str(payload.get("notes") or payload.get("user_notes") or "").strip(),
            "time_range": payload.get("time_range") or {},
            "line_window": line_window,
        },
    }


def analyze_ue_log(
    payload: dict[str, Any],
    *,
    project_root: str | None = None,
    context_current_file: str | None = None,
) -> dict[str, Any]:
    log_source = str(payload.get("log_source") or payload.get("log_path") or "").strip()
    time_range = payload.get("time_range") or {}
    line_window = payload.get("line_window") or {}
    collected_input = _collect_log_input(
        payload,
        project_root=project_root,
        context_current_file=context_current_file,
    )
    raw_text = collected_input["text"]
    lines = [line for line in raw_text.splitlines() if line.strip()]
    lowered = raw_text.lower()

    error_count = sum(1 for line in lines if "error" in line.lower() or "fatal" in line.lower())
    warning_count = sum(1 for line in lines if "warning" in line.lower() or "ensure" in line.lower())
    callstack_lines = [line for line in lines if CALLSTACK_RE.search(line)][:12]
    modules = sorted({match.group(1) for match in MODULE_RE.finditer(raw_text)})[:12]
    resource_paths = sorted(set(RESOURCE_RE.findall(raw_text)))[:12]
    timeline = TIMESTAMP_RE.findall(raw_text)[:12]

    structured_events = []
    for index, line in enumerate(lines[:60], start=1):
        lowered_line = line.lower()
        kind = "info"
        if "fatal" in lowered_line or "error" in lowered_line:
            kind = "error"
        elif "warning" in lowered_line or "ensure" in lowered_line:
            kind = "warning"
        structured_events.append({"line": index, "kind": kind, "message": line[:300]})

    issue_families = []
    findings = []
    suspected_causes = []
    suggestions = []
    for family, config in ISSUE_PATTERNS.items():
        if any(token in lowered for token in config["tokens"]):
            issue_families.append(family)
            findings.append(config["summary"])
            suspected_causes.append(config["summary"])
            suggestions.append(config["suggestion"])

    if not findings and error_count:
        findings.append("The log contains errors but does not match a stronger known failure family yet.")
        suspected_causes.append("Start from the first fatal/error line and correlate with nearby module output.")
        suggestions.append("Narrow to the earliest failing subsystem before expanding the search.")
    if not findings and warning_count:
        findings.append("The log is warning-heavy without a clear crash signature.")
        suspected_causes.append("A soft failure or degraded path may be masking the primary issue.")
        suggestions.append("Review warnings in chronological order and correlate with the user action timeline.")
    if not findings:
        findings.append("No strong failure signature was detected in the provided log text.")
        suspected_causes.append("The provided text may be incomplete or filtered too aggressively.")
        suggestions.append("Provide a larger log window or the crash segment around the first failure.")

    summary = (
        f"Parsed {len(lines)} lines with {error_count} errors and {warning_count} warnings."
        if lines
        else "No log text was provided, so the analyzer could only return input diagnostics."
    )
    return {
        "summary": summary,
        "findings": findings,
        "suspected_causes": suspected_causes,
        "suggestions": suggestions[:5],
        "structured_events": structured_events,
        "log_summary": {
            "line_count": len(lines),
            "error_count": error_count,
            "warning_count": warning_count,
            "callstack_count": len(callstack_lines),
            "module_count": len(modules),
        },
        "issue_families": issue_families,
        "parser_diagnostics": {
            "callstack_lines": callstack_lines,
            "modules": modules,
            "resource_paths": resource_paths,
            "timeline": timeline,
            "input_collection": collected_input["input_context"],
        },
        "input_context": {
            "log_source": log_source,
            "time_range": time_range,
            "line_window": line_window,
            **collected_input["input_context"],
        },
    }
