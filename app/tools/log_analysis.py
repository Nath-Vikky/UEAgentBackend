from __future__ import annotations

import re
from typing import Any

TIMESTAMP_RE = re.compile(r"\[\d{4}\.\d{2}\.\d{2}[-:.\d]*\]")
CALLSTACK_RE = re.compile(r"(?:0x[0-9A-Fa-f]+|!|Callstack)")
MODULE_RE = re.compile(r"\bLog([A-Za-z0-9_]+):")
RESOURCE_RE = re.compile(r"(/Game/[A-Za-z0-9_./-]+)")

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


def analyze_ue_log(payload: dict[str, Any]) -> dict[str, Any]:
    log_source = str(payload.get("log_source") or payload.get("log_path") or "").strip()
    time_range = payload.get("time_range") or {}
    line_window = payload.get("line_window") or {}
    raw_text = "\n".join(
        [
            str(payload.get("log_text") or ""),
            str(payload.get("build_log") or ""),
            str(payload.get("crash_text") or ""),
        ]
    ).strip()
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
        },
        "input_context": {
            "log_source": log_source,
            "time_range": time_range,
            "line_window": line_window,
        },
    }
