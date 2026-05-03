from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.services.code_write_service import build_code_write_plan, execute_code_write_plan


def _workspace() -> Path:
    path = Path(".test-workspace") / f"code-write-unit-{uuid.uuid4().hex}"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_code_write_plan_allows_source_relative_files() -> None:
    workspace = _workspace()
    plan = build_code_write_plan(
        project_root=str(workspace),
        generated_items=[
            {
                "item_id": "generated_1",
                "file_path": "Source/Demo/Public/DemoActor.h",
                "language": "cpp",
                "code": "#pragma once\n",
            }
        ],
    )

    assert plan["status"] == "ready"
    assert plan["summary"]["ready_count"] == 1
    assert plan["files"][0]["relative_path"] == "Source/Demo/Public/DemoActor.h"
    shutil.rmtree(workspace, ignore_errors=True)


def test_code_write_plan_blocks_path_escape() -> None:
    workspace = _workspace()
    plan = build_code_write_plan(
        project_root=str(workspace),
        generated_items=[
            {
                "file_path": "../Outside.cpp",
                "code": "void Bad() {}",
            }
        ],
    )

    assert plan["status"] == "blocked"
    assert plan["summary"]["blocked_count"] == 1
    assert plan["files"][0]["reason"] == "parent_directory_segments_are_not_allowed"
    shutil.rmtree(workspace, ignore_errors=True)


def test_execute_code_write_plan_writes_new_files() -> None:
    workspace = _workspace()
    plan = build_code_write_plan(
        project_root=str(workspace),
        generated_items=[
            {
                "file_path": "Source/Demo/Private/DemoActor.cpp",
                "code": '#include "DemoActor.h"\n',
            }
        ],
    )
    result = execute_code_write_plan(plan)

    assert result["execution_state"] == "files_written"
    assert result["written_to_disk"] is True
    assert (workspace / "Source" / "Demo" / "Private" / "DemoActor.cpp").read_text(
        encoding="utf-8"
    ) == '#include "DemoActor.h"\n'
    shutil.rmtree(workspace, ignore_errors=True)
