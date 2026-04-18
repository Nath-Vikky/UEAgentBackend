from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 5 regression suite.")
    parser.add_argument(
        "--output",
        help="Optional output path for the JSON report. Defaults to storage/artifacts/regression/.",
    )
    return parser.parse_args()


def _default_output_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("storage/artifacts/regression") / f"regression-suite-{stamp}.json"


def _run_step(name: str, command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "name": name,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def main() -> int:
    args = _parse_args()
    python = sys.executable
    steps = [
        _run_step("pytest", [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"]),
        _run_step("ruff", [python, "-m", "ruff", "check", "app", "tests", "scripts", "--no-cache"]),
        _run_step(
            "rag_eval",
            [python, "scripts/run_rag_eval.py", "--dataset", "tests/eval/rag_project_qa_dataset.jsonl"],
        ),
        _run_step(
            "task_eval",
            [python, "scripts/run_task_eval.py"],
        ),
    ]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_ok": all(step["ok"] for step in steps),
        "steps": steps,
    }
    output_path = Path(args.output).resolve() if args.output else _default_output_path().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"overall_ok": report["overall_ok"]}, ensure_ascii=False, indent=2))
    print(f"Saved report to: {output_path}")
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
