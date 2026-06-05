from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SMOKE_SCRIPTS = [
    {
        "suite_id": "blueprint_graph_operation",
        "script": "run_blueprint_graph_operation_smoke.py",
    },
    {
        "suite_id": "editor_operation_chat_bridge",
        "script": "run_editor_operation_chat_bridge_smoke.py",
    },
    {
        "suite_id": "editor_workflow_materialization",
        "script": "run_editor_workflow_materialization_smoke.py",
    },
    {
        "suite_id": "project_inventory_chat",
        "script": "run_project_inventory_chat_smoke.py",
    },
    {
        "suite_id": "tool_registry_readonly",
        "script": "run_tool_registry_readonly_smoke.py",
    },
    {
        "suite_id": "mcp_tcp_adapter",
        "script": "run_mcp_tcp_adapter_smoke.py",
    },
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deterministic UEAgentCraft backend demo smoke suite."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/editor-demo-smoke-suite-latest.json",
        help="JSON report output path. Use '-' to print to stdout without writing a file.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failing smoke suite.",
    )
    parser.add_argument(
        "--include-child-reports",
        action="store_true",
        help="Embed full child smoke reports instead of compact suite summaries.",
    )
    return parser.parse_args()


def _report_from_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return dict(json.loads(text))
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return dict(json.loads(text[start : end + 1]))
            except json.JSONDecodeError:
                return {}
    return {}


def _run_suite(
    *,
    suite_id: str,
    script: str,
    backend_root: Path,
    include_child_report: bool,
) -> dict[str, Any]:
    command = [sys.executable, str(backend_root / "scripts" / script), "--output", "-"]
    completed = subprocess.run(
        command,
        cwd=backend_root,
        check=False,
        capture_output=True,
        text=True,
    )
    report = _report_from_stdout(completed.stdout)
    summary = dict(report.get("summary") or {})
    ok = completed.returncode == 0 and bool(report.get("overall_ok"))
    suite_result = {
        "suite_id": suite_id,
        "script": script,
        "return_code": completed.returncode,
        "ok": ok,
        "case_count": int(summary.get("case_count") or 0),
        "passed": int(summary.get("passed") or 0),
        "failed": int(summary.get("failed") or 0),
        "report_generated_at": report.get("generated_at"),
        "report_mode": report.get("mode"),
        "report_summary": summary,
        "report_notes": list(report.get("notes") or []),
    }
    if include_child_report or not ok:
        suite_result["stderr_tail"] = completed.stderr.strip().splitlines()[-20:]
    if include_child_report:
        suite_result["report"] = report
    return suite_result


def _emit_report(report: dict[str, Any], output: str) -> None:
    report_json = json.dumps(report, indent=2, ensure_ascii=False)
    if output == "-":
        print(report_json)
        return
    output_path = Path(output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_json, encoding="utf-8")
    except OSError as exc:
        print(f"WARNING: could not write smoke suite report to {output_path}: {exc}")
    print(report_json)


def main() -> int:
    args = _parse_args()
    backend_root = Path(__file__).resolve().parents[1]
    suites: list[dict[str, Any]] = []
    for item in SMOKE_SCRIPTS:
        result = _run_suite(
            suite_id=str(item["suite_id"]),
            script=str(item["script"]),
            backend_root=backend_root,
            include_child_report=args.include_child_reports,
        )
        suites.append(result)
        if args.fail_fast and not result["ok"]:
            break

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic_no_ue_no_llm",
        "overall_ok": all(item["ok"] for item in suites),
        "summary": {
            "suite_count": len(suites),
            "suite_passed": sum(1 for item in suites if item["ok"]),
            "suite_failed": sum(1 for item in suites if not item["ok"]),
            "case_count": sum(int(item.get("case_count") or 0) for item in suites),
            "passed": sum(int(item.get("passed") or 0) for item in suites),
            "failed": sum(int(item.get("failed") or 0) for item in suites),
        },
        "suites": suites,
        "notes": [
            "This suite aggregates backend-only deterministic smoke checks.",
            "It does not launch Unreal Editor, execute editor writes, or call a live LLM.",
            "Each child smoke still owns its detailed case coverage.",
        ],
    }
    _emit_report(report, args.output)
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
