from __future__ import annotations

import re
from typing import Any

FRAME_MS_RE = re.compile(r"(?:frame(?: time)?|frametime)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
THREAD_MS_RE = re.compile(r"(game|render|rhi)\s*thread\s*[:=]?\s*(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
DRAW_CALL_RE = re.compile(r"draw\s*calls?\s*[:=]?\s*(\d+)", re.IGNORECASE)
MEMORY_MB_RE = re.compile(r"(?:used|peak|total)?\s*memory\s*[:=]?\s*(\d+(?:\.\d+)?)\s*mb", re.IGNORECASE)


def _float_matches(pattern, text: str) -> list[float]:
    return [float(match.group(1)) for match in pattern.finditer(text)]


def analyze_memory_perf_signals(payload: dict[str, Any]) -> dict[str, Any]:
    evidence_text = "\n".join(
        [
            str(payload.get("report_text") or ""),
            str(payload.get("hitch_description") or ""),
            str(payload.get("profiler_text") or ""),
            str(payload.get("memreport_text") or ""),
            str(payload.get("insights_summary") or ""),
        ]
    ).strip()
    lowered = evidence_text.lower()

    frame_times = _float_matches(FRAME_MS_RE, evidence_text)
    thread_times = [
        {"thread": match.group(1).lower(), "ms": float(match.group(2))}
        for match in THREAD_MS_RE.finditer(evidence_text)
    ]
    draw_calls = [int(match.group(1)) for match in DRAW_CALL_RE.finditer(evidence_text)]
    memory_mb = _float_matches(MEMORY_MB_RE, evidence_text)

    suspicious_points: list[dict[str, Any]] = []
    probable_causes: list[str] = []
    optimization_suggestions: list[str] = []

    peak_frame = max(frame_times) if frame_times else 0.0
    peak_memory = max(memory_mb) if memory_mb else 0.0
    peak_draw_calls = max(draw_calls) if draw_calls else 0

    if peak_frame >= 33.0:
        suspicious_points.append({"metric": "frame_time_ms", "value": peak_frame, "severity": "high"})
        probable_causes.append("Frame time is well above 33ms, which suggests a visible hitch or low frame rate.")
        optimization_suggestions.append("Focus on the hottest thread and look for blocking work on the frame path.")
    elif peak_frame >= 16.6:
        suspicious_points.append({"metric": "frame_time_ms", "value": peak_frame, "severity": "medium"})
        probable_causes.append("Frame time exceeds a 60 FPS budget and may need targeted optimization.")
        optimization_suggestions.append("Inspect whether the bottleneck is on the game, render, or RHI thread.")

    for item in thread_times:
        if item["ms"] >= 12.0:
            suspicious_points.append(
                {
                    "metric": f"{item['thread']}_thread_ms",
                    "value": item["ms"],
                    "severity": "medium",
                }
            )

    if peak_draw_calls >= 3000:
        suspicious_points.append({"metric": "draw_calls", "value": peak_draw_calls, "severity": "medium"})
        probable_causes.append("Draw-call count is high enough to warrant batching or visibility review.")
        optimization_suggestions.append("Investigate instancing, culling, and material diversity.")

    if peak_memory >= 2048:
        suspicious_points.append({"metric": "memory_mb", "value": peak_memory, "severity": "high"})
        probable_causes.append("Peak memory usage is elevated and may be driving paging or OOM risk.")
        optimization_suggestions.append("Inspect streaming, residency, and large transient allocations.")

    if "streaming" in lowered or "tryload" in lowered or "loadobject" in lowered:
        probable_causes.append("The evidence references loading or streaming work, which may contribute to hitches.")
        optimization_suggestions.append("Check for synchronous loading on critical gameplay paths.")

    if not suspicious_points:
        suspicious_points.append({"metric": "evidence_quality", "value": 0, "severity": "low"})
        probable_causes.append("No strong metric hotspot was parsed from the provided text.")
        optimization_suggestions.append("Provide a memreport, Insights excerpt, or stat dump with concrete timings.")

    evidence_summary = [line.strip() for line in evidence_text.splitlines() if line.strip()][:12]
    summary = (
        f"Parsed performance evidence with peak frame time {peak_frame:.1f} ms and peak memory {peak_memory:.1f} MB."
        if evidence_text
        else "No performance evidence text was provided, so the analyzer returned only input diagnostics."
    )
    return {
        "summary": summary,
        "suspicious_points": suspicious_points,
        "probable_causes": probable_causes[:6],
        "optimization_suggestions": optimization_suggestions[:6],
        "evidence_summary": evidence_summary,
        "metric_summary": {
            "peak_frame_time_ms": peak_frame,
            "peak_memory_mb": peak_memory,
            "peak_draw_calls": peak_draw_calls,
            "thread_times": thread_times[:8],
        },
        "bottleneck_summary": {
            "dominant_thread": max(thread_times, key=lambda item: item["ms"])["thread"] if thread_times else None,
            "dominant_thread_ms": max(thread_times, key=lambda item: item["ms"])["ms"] if thread_times else 0.0,
        },
        "parser_diagnostics": {
            "frame_samples": len(frame_times),
            "thread_samples": len(thread_times),
            "draw_call_samples": len(draw_calls),
            "memory_samples": len(memory_mb),
        },
    }
