from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.schemas.requests import UnifiedTaskRequest
from app.tools.project_file import (
    project_file_candidate,
    read_project_file,
    read_project_file_tool,
    should_read_project_file,
)


@contextmanager
def _runtime_root(name: str) -> Iterator[Path]:
    root = Path(".test-runtime") / f"{name}-{uuid.uuid4().hex}"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _request(project_root: Path, current_file: str = "Source/Demo.cpp") -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type="agent_chat",
        session={
            "session_id": "project_file_tool_test",
            "messages": [{"role": "user", "content": "解释当前文件", "language": "auto"}],
        },
        context={
            "active_panel": "AgentChat",
            "project_name": "DemoProject",
            "project_root": str(project_root),
            "current_file": current_file,
        },
        payload={"user_query": "解释当前文件"},
        ui_state={"active_view": "user", "selected_panel": "AgentChat"},
        runtime_options={"profile_id": "default", "stream": False, "debug": True},
    )


def test_project_file_candidate_reads_context_aliases() -> None:
    with _runtime_root("project-file-candidate") as project_root:
        request = _request(project_root)

        candidate = project_file_candidate(request)

        assert candidate == {
            "project_root": str(project_root),
            "file_path": "Source/Demo.cpp",
            "max_bytes": 40_000,
        }
        assert should_read_project_file(request=request, query="请解释当前文件") is True


def test_read_project_file_blocks_outside_project_root() -> None:
    with _runtime_root("project-file-outside") as project_root:
        outside = project_root.parent / f"Outside-{uuid.uuid4().hex}.cpp"

        result = read_project_file(
            project_root=str(project_root),
            file_path=str(outside.resolve()),
        )

    assert result["status"] == "blocked"
    assert result["reason"] == "file_outside_project_root"


def test_read_project_file_blocks_unsupported_suffix() -> None:
    with _runtime_root("project-file-suffix") as project_root:
        file_path = project_root / "Saved" / "Binary.uasset"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"binary")

        result = read_project_file(project_root=str(project_root), file_path="Saved/Binary.uasset")

    assert result["status"] == "blocked"
    assert result["reason"] == "unsupported_file_extension"


def test_read_project_file_tool_returns_text_excerpt() -> None:
    with _runtime_root("project-file-read") as project_root:
        source = project_root / "Source"
        source.mkdir()
        (source / "Demo.cpp").write_text("void ADemo::BeginPlay() {}", encoding="utf-8")

        result = read_project_file_tool(_request(project_root))

    assert result["status"] == "completed"
    assert result["reason"] == "read_completed"
    assert result["file_path"] == "Source/Demo.cpp"
    assert "BeginPlay" in result["text_excerpt"]
