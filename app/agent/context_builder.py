from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest


def build_context_summary(request: UnifiedTaskRequest) -> dict[str, Any]:
    return {
        "project_name": request.context.project_name,
        "active_panel": request.context.active_panel,
        "current_file": request.context.current_file,
        "current_module": request.context.current_module,
        "selected_assets": request.context.selected_assets,
        "recent_open_files": request.context.recent_open_files,
        "selected_panel": request.ui_state.selected_panel,
    }

